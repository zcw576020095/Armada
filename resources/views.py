import json

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from clusters.models import Cluster
from clusters.k8s_client import k8s_pool
from clusters.pod_logs import fetch_pod_logs
from resources.models import K8sResourceCache
from resources.sync_service import trigger_immediate_sync
from .k8s_resources import K8sResourceManager


CACHE_TTL_SECONDS = 120


def _get_mgr(pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    return cluster, K8sResourceManager(cluster)


def _cache_fresh(cache_obj):
    """判断缓存是否还在有效期内。"""
    if not cache_obj:
        return False
    return (timezone.now() - cache_obj.synced_at).total_seconds() < CACHE_TTL_SECONDS


# ─── Namespaces ──────────────────────────────────────────────

def namespace_list(request, pk):
    cluster, _ = _get_mgr(pk)
    can_edit = getattr(request, 'user_can_edit', True)
    can_delete = getattr(request, 'user_can_delete', True)
    return render(request, 'resources/namespace_list.html', {
        'cluster': cluster, 'can_edit': can_edit, 'can_delete': can_delete,
    })


def namespace_list_api(request, pk):
    cluster, _ = _get_mgr(pk)
    try:
        cache_obj = K8sResourceCache.objects.filter(
            cluster_id=cluster.pk,
            resource_type='namespace',
            namespace=''
        ).first()

        if _cache_fresh(cache_obj):
            return JsonResponse({
                'namespaces': cache_obj.data,
                'cached': True,
                'synced_at': cache_obj.synced_at.isoformat(),
            })

        # 缓存未命中，触发同步并返回空数据（前端会重试）
        trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({'namespaces': [], 'syncing': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def namespace_create(request, pk):
    cluster, mgr = _get_mgr(pk)
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)
    try:
        from kubernetes import client
        body = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
        created = mgr.core_v1.create_namespace(body, _request_timeout=10)
        # wait=True：等同步完成再返回，保证前端紧接着 list 能拿到新建项
        trigger_immediate_sync(cluster, 'namespace', wait=True)
        return JsonResponse({
            'success': True,
            # 返回新建项供前端乐观插入（即使 sync wait 超时也能立即显示）
            'resource': {
                'name': created.metadata.name,
                'namespace': '',
                'status': (created.status.phase if created.status else 'Active') or 'Active',
                'created': created.metadata.creation_timestamp.strftime('%Y-%m-%d %H:%M') if created.metadata.creation_timestamp else '',
                'age': '0s',
            },
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def namespace_delete(request, pk, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.delete_resource('namespace', name)
        # wait=True：等同步完成再返回，前端 list 能立即看到 Terminating 状态
        trigger_immediate_sync(cluster, 'namespace', wait=True)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Generic resource list helper ────────────────────────────

def _workload_list(request, pk, template):
    """Generic list view for namespaced workloads - renders skeleton, data via API."""
    cluster = get_object_or_404(Cluster, pk=pk)
    can_edit = getattr(request, 'user_can_edit', True)
    can_delete = getattr(request, 'user_can_delete', True)

    return render(request, template, {
        'cluster': cluster,
        'can_edit': can_edit,
        'can_delete': can_delete,
    })


def _workload_list_api(request, pk, resource_type):
    """AJAX API: 优先从数据库缓存读取（毫秒级），缓存未命中时触发同步。"""
    cluster = get_object_or_404(Cluster, pk=pk)
    ns_filter = request.GET.get('namespace', '')

    try:
        cache_obj = K8sResourceCache.objects.filter(
            cluster_id=cluster.pk,
            resource_type=resource_type,
            namespace=''
        ).first()

        ns_cache = K8sResourceCache.objects.filter(
            cluster_id=cluster.pk,
            resource_type='namespace',
            namespace=''
        ).first()

        if _cache_fresh(cache_obj):
            resources = cache_obj.data
            if ns_filter:
                resources = [r for r in resources if r.get('namespace') == ns_filter]

            ns_list = [n['name'] for n in ns_cache.data] if ns_cache else []

            return JsonResponse({
                'resources': resources,
                'namespaces': ns_list,
                'cached': True,
                'synced_at': cache_obj.synced_at.isoformat(),
            })

        # 缓存未命中，触发同步
        trigger_immediate_sync(cluster, resource_type)
        if not ns_cache:
            trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({'resources': [], 'namespaces': [], 'syncing': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Deployments ─────────────────────────────────────────────

def deployment_list(request, pk):
    return _workload_list(request, pk, 'resources/deployment_list.html')


def deployment_list_api(request, pk):
    return _workload_list_api(request, pk, 'deployment')


@require_POST
def deployment_scale(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body)
        replicas = int(data.get('replicas', 0))
        mgr.scale_deployment(name, ns, replicas)
        trigger_immediate_sync(cluster, 'deployment')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def deployment_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_deployment(name, ns)
        trigger_immediate_sync(cluster, 'deployment')
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── StatefulSets ────────────────────────────────────────────

def statefulset_list(request, pk):
    return _workload_list(request, pk, 'resources/statefulset_list.html')


def statefulset_list_api(request, pk):
    return _workload_list_api(request, pk, 'statefulset')


@require_POST
def statefulset_scale(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body)
        replicas = int(data.get('replicas', 0))
        mgr.scale_statefulset(name, ns, replicas)
        trigger_immediate_sync(cluster, 'statefulset')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def statefulset_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_statefulset(name, ns)
        trigger_immediate_sync(cluster, 'statefulset')
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── DaemonSets ──────────────────────────────────────────────

def daemonset_list(request, pk):
    return _workload_list(request, pk, 'resources/daemonset_list.html')


def daemonset_list_api(request, pk):
    return _workload_list_api(request, pk, 'daemonset')


# ─── Pods ────────────────────────────────────────────────────

def pod_list(request, pk):
    return _workload_list(request, pk, 'resources/pod_list.html')


def pod_list_api(request, pk):
    return _workload_list_api(request, pk, 'pod')


def pod_logs(request, pk, namespace, pod_name):
    cluster = get_object_or_404(Cluster, pk=pk)
    return fetch_pod_logs(cluster, namespace, pod_name, request.GET)


# ─── Services ────────────────────────────────────────────────

def service_list(request, pk):
    return _workload_list(request, pk, 'resources/service_list.html')


def service_list_api(request, pk):
    return _workload_list_api(request, pk, 'service')


# ─── Ingresses ───────────────────────────────────────────────

def ingress_list(request, pk):
    return _workload_list(request, pk, 'resources/ingress_list.html')


def ingress_list_api(request, pk):
    return _workload_list_api(request, pk, 'ingress')


# ─── ConfigMaps ──────────────────────────────────────────────

def configmap_list(request, pk):
    return _workload_list(request, pk, 'resources/configmap_list.html')


def configmap_list_api(request, pk):
    return _workload_list_api(request, pk, 'configmap')


# ─── Secrets ─────────────────────────────────────────────────

def secret_list(request, pk):
    return _workload_list(request, pk, 'resources/secret_list.html')


def secret_list_api(request, pk):
    return _workload_list_api(request, pk, 'secret')


# ─── PVCs ────────────────────────────────────────────────────

def pvc_list(request, pk):
    return _workload_list(request, pk, 'resources/pvc_list.html')


def pvc_list_api(request, pk):
    return _workload_list_api(request, pk, 'persistentvolumeclaim')


# ─── Generic YAML API ────────────────────────────────────────

def resource_yaml_api(request, pk, resource_type, name, ns=None):
    """GET: return YAML; POST: apply YAML."""
    cluster, mgr = _get_mgr(pk)

    if request.method == 'GET':
        try:
            yaml_content = mgr.get_resource_yaml(resource_type, name, ns)
            return JsonResponse({'yaml': yaml_content})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            yaml_content = data.get('yaml', '')
            result = mgr.apply_yaml(yaml_content)
            if result['success']:
                trigger_immediate_sync(cluster, resource_type)
                return JsonResponse(result)
            return JsonResponse(result, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ─── Generic Delete API ──────────────────────────────────────

@require_POST
def resource_delete_api(request, pk, resource_type, name, ns=None):
    cluster, mgr = _get_mgr(pk)
    # force=1 时对 Pod 启用强制删除（跳过 30 秒优雅退出期，立即清除）
    force = request.GET.get('force') == '1' or request.POST.get('force') == '1'
    try:
        mgr.delete_resource(resource_type, name, ns, force=force)
        # wait=True：删除是关键写操作，等同步完成再返回让前端立即看到结果
        trigger_immediate_sync(cluster, resource_type, wait=True)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
