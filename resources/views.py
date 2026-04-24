import json

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from clusters.models import Cluster
from .k8s_resources import K8sResourceManager


def _get_mgr(pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    return cluster, K8sResourceManager(cluster)


def _ts(obj):
    """Extract creation timestamp as string."""
    ts = getattr(obj.metadata, 'creation_timestamp', None)
    return ts.strftime('%Y-%m-%d %H:%M') if ts else '-'


# ─── Namespaces ──────────────────────────────────────────────

def namespace_list(request, pk):
    cluster, _ = _get_mgr(pk)
    can_edit = getattr(request, 'user_can_edit', True)
    can_delete = getattr(request, 'user_can_delete', True)
    return render(request, 'resources/namespace_list.html', {
        'cluster': cluster, 'can_edit': can_edit, 'can_delete': can_delete,
    })


def namespace_list_api(request, pk):
    cluster, mgr = _get_mgr(pk)
    try:
        from resources.models import K8sResourceCache
        from django.utils import timezone

        cache_obj = K8sResourceCache.objects.filter(
            cluster_id=cluster.pk,
            resource_type='namespace',
            namespace=''
        ).first()

        if cache_obj and (timezone.now() - cache_obj.synced_at).seconds < 120:
            return JsonResponse({
                'namespaces': cache_obj.data,
                'cached': True,
                'synced_at': cache_obj.synced_at.isoformat(),
            })

        # 缓存未命中，触发同步并返回空数据（前端会重试）
        from resources.sync_service import trigger_immediate_sync
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
        mgr.core_v1.create_namespace(body, _request_timeout=10)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def namespace_delete(request, pk, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.delete_resource('namespace', name)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Generic resource list helper ────────────────────────────

def _workload_list(request, pk, resource_type, template, extra_fields_fn=None):
    """Generic list view for namespaced workloads - renders skeleton, data via API."""
    cluster, mgr = _get_mgr(pk)
    can_edit = getattr(request, 'user_can_edit', True)
    can_delete = getattr(request, 'user_can_delete', True)

    return render(request, template, {
        'cluster': cluster,
        'resource_type': resource_type,
        'can_edit': can_edit,
        'can_delete': can_delete,
    })


def _workload_list_api(request, pk, resource_type, extra_fields_fn=None):
    """AJAX API: 优先从数据库缓存读取（毫秒级），缓存未命中时触发同步。"""
    from resources.models import K8sResourceCache
    from django.utils import timezone

    cluster, mgr = _get_mgr(pk)
    ns_filter = request.GET.get('namespace', '')

    try:
        # 优先从数据库缓存读取
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

        if cache_obj and (timezone.now() - cache_obj.synced_at).seconds < 120:
            resources = cache_obj.data
            # 按 namespace 过滤
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
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, resource_type)
        if not ns_cache:
            trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({'resources': [], 'namespaces': [], 'syncing': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Deployments ─────────────────────────────────────────────

def _deploy_fields(item):
    spec = item.spec or {}
    status = item.status or {}
    return {
        'replicas': spec.replicas or 0,
        'ready_replicas': status.ready_replicas or 0,
        'available': status.available_replicas or 0,
        'image': (spec.template.spec.containers[0].image
                  if spec.template and spec.template.spec and spec.template.spec.containers
                  else '-'),
    }


def deployment_list(request, pk):
    return _workload_list(request, pk, 'deployment',
                          'resources/deployment_list.html', _deploy_fields)


def deployment_list_api(request, pk):
    return _workload_list_api(request, pk, 'deployment', _deploy_fields)


@require_POST
def deployment_scale(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body)
        replicas = int(data.get('replicas', 0))
        mgr.scale_deployment(name, ns, replicas)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'deployment')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def deployment_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_deployment(name, ns)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'deployment')
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── StatefulSets ────────────────────────────────────────────

def _sts_fields(item):
    spec = item.spec or {}
    status = item.status or {}
    return {
        'replicas': spec.replicas or 0,
        'ready_replicas': status.ready_replicas or 0,
        'image': (spec.template.spec.containers[0].image
                  if spec.template and spec.template.spec and spec.template.spec.containers
                  else '-'),
    }


def statefulset_list(request, pk):
    return _workload_list(request, pk, 'statefulset',
                          'resources/statefulset_list.html', _sts_fields)


def statefulset_list_api(request, pk):
    return _workload_list_api(request, pk, 'statefulset', _sts_fields)


@require_POST
def statefulset_scale(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body)
        replicas = int(data.get('replicas', 0))
        mgr.scale_statefulset(name, ns, replicas)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'statefulset')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def statefulset_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_statefulset(name, ns)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, 'statefulset')
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── DaemonSets ──────────────────────────────────────────────

def _ds_fields(item):
    status = item.status or {}
    return {
        'desired': status.desired_number_scheduled or 0,
        'current': status.current_number_scheduled or 0,
        'ready': status.number_ready or 0,
        'image': (item.spec.template.spec.containers[0].image
                  if item.spec and item.spec.template and item.spec.template.spec
                  and item.spec.template.spec.containers else '-'),
    }


def daemonset_list(request, pk):
    return _workload_list(request, pk, 'daemonset',
                          'resources/daemonset_list.html', _ds_fields)


def daemonset_list_api(request, pk):
    return _workload_list_api(request, pk, 'daemonset', _ds_fields)


# ─── Pods ────────────────────────────────────────────────────

def _pod_fields(item):
    status = item.status or {}
    containers = item.spec.containers if item.spec else []
    total = len(containers)
    ready = sum(1 for cs in (status.container_statuses or []) if cs.ready)
    restarts = sum(cs.restart_count for cs in (status.container_statuses or []))
    return {
        'status_phase': status.phase or 'Unknown',
        'ready_str': f'{ready}/{total}',
        'restarts': restarts,
        'node': item.spec.node_name or '-',
        'ip': status.pod_ip or '-',
    }


def pod_list(request, pk):
    return _workload_list(request, pk, 'pod',
                          'resources/pod_list.html', _pod_fields)


def pod_list_api(request, pk):
    return _workload_list_api(request, pk, 'pod', _pod_fields)


def pod_logs(request, pk, namespace, pod_name):
    cluster = get_object_or_404(Cluster, pk=pk)
    container = request.GET.get('container', '')
    tail_lines = int(request.GET.get('tail_lines', 200))
    previous = request.GET.get('previous', 'false') == 'true'
    try:
        from clusters.k8s_client import k8s_pool
        core = k8s_pool.core_v1(cluster)

        if not container:
            pod = core.read_namespaced_pod(pod_name, namespace, _request_timeout=5)
            if pod.spec.containers:
                container = pod.spec.containers[0].name

        kwargs = {
            'name': pod_name,
            'namespace': namespace,
            'tail_lines': tail_lines,
            '_request_timeout': 10,
        }
        if previous:
            kwargs['previous'] = True
        if container:
            kwargs['container'] = container

        logs = core.read_namespaced_pod_log(**kwargs)
        return JsonResponse({'success': True, 'logs': logs or '', 'container': container, 'previous': previous})
    except Exception as e:
        err_str = str(e)
        if previous and ('previous terminated' in err_str.lower() or 'not found' in err_str.lower() or 'previous' in err_str.lower()):
            return JsonResponse({'success': True, 'logs': '', 'container': container, 'previous': previous, 'no_previous': True})
        return JsonResponse({'error': err_str}, status=500)


# ─── Services ────────────────────────────────────────────────

def _svc_fields(item):
    spec = item.spec or {}
    ports = ', '.join(
        f"{p.port}" + (f":{p.node_port}" if p.node_port else "") + f"/{p.protocol}"
        for p in (spec.ports or [])
    )
    return {
        'type': spec.type or '-',
        'cluster_ip': spec.cluster_ip or '-',
        'ports': ports or '-',
    }


def service_list(request, pk):
    return _workload_list(request, pk, 'service',
                          'resources/service_list.html', _svc_fields)


def service_list_api(request, pk):
    return _workload_list_api(request, pk, 'service', _svc_fields)


# ─── Ingresses ───────────────────────────────────────────────

def _ingress_fields(item):
    spec = item.spec or {}
    rules = []
    for rule in (spec.rules or []):
        host = rule.host or '*'
        for path in (rule.http.paths if rule.http else []):
            backend = path.backend
            svc_name = '-'
            svc_port = '-'
            if backend and backend.service:
                svc_name = backend.service.name or '-'
                svc_port = str(backend.service.port.number if backend.service.port else '-')
            rules.append(f"{host}{path.path or '/'} → {svc_name}:{svc_port}")
    return {
        'rules_str': '; '.join(rules) if rules else '-',
        'class_name': spec.ingress_class_name or '-',
    }


def ingress_list(request, pk):
    return _workload_list(request, pk, 'ingress',
                          'resources/ingress_list.html', _ingress_fields)


def ingress_list_api(request, pk):
    return _workload_list_api(request, pk, 'ingress', _ingress_fields)


# ─── ConfigMaps ──────────────────────────────────────────────

def _cm_fields(item):
    data = item.data or {}
    return {'key_count': len(data), 'keys': list(data.keys())}


def configmap_list(request, pk):
    return _workload_list(request, pk, 'configmap',
                          'resources/configmap_list.html', _cm_fields)


def configmap_list_api(request, pk):
    return _workload_list_api(request, pk, 'configmap', _cm_fields)


# ─── Secrets ─────────────────────────────────────────────────

def _secret_fields(item):
    data = item.data or {}
    return {'type': item.type or 'Opaque', 'key_count': len(data), 'keys': list(data.keys())}


def secret_list(request, pk):
    return _workload_list(request, pk, 'secret',
                          'resources/secret_list.html', _secret_fields)


def secret_list_api(request, pk):
    return _workload_list_api(request, pk, 'secret', _secret_fields)


# ─── PVCs ────────────────────────────────────────────────────

def _pvc_fields(item):
    spec = item.spec or {}
    status = item.status or {}
    storage = '-'
    if spec.resources and spec.resources.requests:
        storage = spec.resources.requests.get('storage', '-')
    return {
        'status_phase': status.phase or 'Unknown',
        'storage': storage,
        'access_modes': ', '.join(spec.access_modes or []),
        'storage_class': spec.storage_class_name or '-',
    }


def pvc_list(request, pk):
    return _workload_list(request, pk, 'persistentvolumeclaim',
                          'resources/pvc_list.html', _pvc_fields)


def pvc_list_api(request, pk):
    return _workload_list_api(request, pk, 'persistentvolumeclaim', _pvc_fields)


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
                from resources.sync_service import trigger_immediate_sync
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
    try:
        mgr.delete_resource(resource_type, name, ns)
        from resources.sync_service import trigger_immediate_sync
        trigger_immediate_sync(cluster, resource_type)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
