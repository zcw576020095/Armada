import json
import logging

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from clusters.models import Cluster
from clusters.k8s_client import k8s_pool
from clusters.pod_logs import fetch_pod_logs
from resources.models import K8sResourceCache
from resources.sync_service import trigger_immediate_sync, get_sync_error

logger = logging.getLogger(__name__)


def _serialize_resource(mgr, kind, name, namespace=None):
    """读取资源最新状态并序列化为前端列表格式（给 scale/restart 等写操作 view 用）。

    让前端拿到 K8s 最新值立即更新 UI（markUpdated），不必再依赖
    trigger_immediate_sync 异步同步 + cache 同步窗口。
    """
    try:
        from resources.sync_service import _serialize_item
        obj = mgr.get_resource(kind, name, namespace)
        return _serialize_item(kind, obj)
    except Exception as e:
        logger.warning(f'Failed to serialize {kind} {name}: {e}')
        return None
from .k8s_resources import K8sResourceManager


CACHE_TTL_SECONDS = 120

# namespace 删除/强制完成时一并刷的资源类型 —— 这些资源是 ns 范围内的，
# ns 进入 Terminating / 被清掉时它们要么也在被级联删，要么已经不存在了，
# 必须同步刷一遍 cache，否则 deployment / pod 等列表会保留陈旧条目。
NS_CASCADE_SYNC_KINDS = (
    'deployment', 'statefulset', 'daemonset', 'pod',
    'service', 'ingress', 'configmap', 'secret', 'persistentvolumeclaim',
)


def _purge_namespace_from_cache(cluster, ns_name):
    """删 ns 后立即把 cache 里 namespace=ns_name 的资源条目剔除。

    namespace controller 清理 ns 内资源是异步过程（秒级到分钟级），期间
    K8s API 还会返回这些 deployment/pod，sync 出来的 cache 也会有。
    主动剔除 cache 让前端列表立刻反映"该 ns 已无资源"，之后定时 sync
    按 K8s 真实状态再覆盖（K8s 真清完后正好对得上）。
    """
    purged = 0
    for kind in NS_CASCADE_SYNC_KINDS:
        cache_obj = K8sResourceCache.objects.filter(
            cluster_id=cluster.pk, resource_type=kind, namespace=''
        ).first()
        if not cache_obj or not isinstance(cache_obj.data, list):
            continue
        new_data = [r for r in cache_obj.data if r.get('namespace') != ns_name]
        if len(new_data) != len(cache_obj.data):
            cache_obj.data = new_data
            cache_obj.save(update_fields=['data', 'synced_at'])
            purged += 1
    if purged:
        logger.info(f'[ns-purge] cluster={cluster.name} ns={ns_name} kinds_pruned={purged}')


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

        sync_err = get_sync_error(cluster.pk)

        if _cache_fresh(cache_obj):
            return JsonResponse({
                'namespaces': cache_obj.data,
                'cached': True,
                'synced_at': cache_obj.synced_at.isoformat(),
                # 即使 cache 是新鲜的，也透传一下 sync 错误（只影响后续刷新，
                # 让前端能给一个温和的横幅提醒"集群连接出问题，列表可能不是最新的"）
                'cluster_error': sync_err,
            })

        # 缓存未命中
        trigger_immediate_sync(cluster, 'namespace')
        # 区分两种状态：从未同步过 vs 最近一次同步失败 —— 前端给不同提示
        return JsonResponse({
            'namespaces': [],
            'syncing': True,
            'cluster_error': sync_err,
            'never_synced': cache_obj is None,
        })
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
        # wait=True：保证 ns cache 立刻刷新；其他页面（如 deployment 列表）的 ns 下拉
        # 是从 ns cache 全集来的，不 wait 会出现"刚建完切过去看不到"
        trigger_immediate_sync(cluster, 'namespace', wait=True)
        return JsonResponse({
            'success': True,
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
        # 立即把 cache 里属于该 ns 的资源条目剔除（K8s 控制器清理是异步的，
        # 不主动 purge 的话用户切到 deployment 页会看到"已删 ns 的 deployment 还在"）
        _purge_namespace_from_cache(cluster, name)
        trigger_immediate_sync(cluster, 'namespace', wait=True)
        # 仍触发 cascade 资源的 sync —— 让 cache 跟 K8s 真实状态最终对齐
        for kind in NS_CASCADE_SYNC_KINDS:
            trigger_immediate_sync(cluster, kind)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def namespace_force_finalize(request, pk, name):
    """强制清空 namespace 的 finalizers，让 K8s 立即从 etcd 删除该 namespace。

    应急操作：当 namespace 长时间卡在 Terminating 状态（通常因为 APIService
    不可用、controller 卡死、或 finalizer hook 不响应）时使用。
    ⚠️ 副作用：K8s 不会再清理 namespace 内部资源，可能产生孤儿对象。
    仅当 namespace 内确实没有重要资源、且确认是 K8s 集群层面的清理卡死时使用。
    """
    cluster, mgr = _get_mgr(pk)
    from kubernetes.client.exceptions import ApiException
    try:
        try:
            ns = mgr.core_v1.read_namespace(name, _request_timeout=5)
        except ApiException as e:
            if e.status == 404:
                # K8s 已经删干净了，前端列表只是 cache 没刷到；同步一下让它消失
                _purge_namespace_from_cache(cluster, name)
                trigger_immediate_sync(cluster, 'namespace', wait=True)
                for kind in NS_CASCADE_SYNC_KINDS:
                    trigger_immediate_sync(cluster, kind)
                return JsonResponse({
                    'success': True,
                    'message': 'Namespace 已不存在（K8s 已清理完成），列表即将刷新',
                })
            raise

        if not ns.spec or not ns.spec.finalizers:
            return JsonResponse({
                'success': True,
                'message': 'Namespace 没有 finalizers，应该很快从 etcd 消失（如未消失说明是其他控制器问题）',
            })

        # 调 /finalize 子资源 PUT 一个 finalizers=[] 的 spec —— 等价于 kubectl edit ns 后清空
        ns.spec.finalizers = []
        api_client = mgr.core_v1.api_client
        api_client.call_api(
            f'/api/v1/namespaces/{name}/finalize',
            'PUT',
            body=api_client.sanitize_for_serialization(ns),
            response_type='object',
            header_params={'Content-Type': 'application/json', 'Accept': 'application/json'},
            auth_settings=['BearerToken'],
            _return_http_data_only=True,
            _request_timeout=10,
        )
        _purge_namespace_from_cache(cluster, name)
        trigger_immediate_sync(cluster, 'namespace', wait=True)
        for kind in NS_CASCADE_SYNC_KINDS:
            trigger_immediate_sync(cluster, kind)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': f'强制完成失败：{e}'}, status=500)


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

        sync_err = get_sync_error(cluster.pk)

        # 找出所有处于 Terminating 状态的 namespace —— 用户已经发起删除，
        # K8s namespace controller 还在异步清理内部资源，期间 deployment / pod 等
        # cache 还会反复出现。从用户视角这些 ns 已"不存在"，所以列表里也不该展示
        # 这些 ns 的资源（也不该出现在 ns 下拉里）。
        terminating_ns = set()
        if ns_cache and isinstance(ns_cache.data, list):
            terminating_ns = {n['name'] for n in ns_cache.data if n.get('status') == 'Terminating'}

        if _cache_fresh(cache_obj):
            resources = cache_obj.data
            if terminating_ns:
                resources = [r for r in resources if r.get('namespace') not in terminating_ns]
            # 注意：先用未做 ns_filter 的 resources 计算下拉列表，再做 ns 过滤渲染表格
            ns_set = {r.get('namespace') for r in resources if r.get('namespace')}
            # 用户当前已选的 ns 即使现在没数据，也保留在下拉里，否则 select
            # 显示的会是空白，迷惑
            if ns_filter:
                ns_set.add(ns_filter)
            ns_list = sorted(ns_set)
            if ns_filter:
                resources = [r for r in resources if r.get('namespace') == ns_filter]

            return JsonResponse({
                'resources': resources,
                # 下拉只展示"当前资源类型确实有实例"的 ns —— 否则用户筛了之后是空，没意义
                'namespaces': ns_list,
                'cached': True,
                'synced_at': cache_obj.synced_at.isoformat(),
                'cluster_error': sync_err,
            })

        # 缓存未命中，触发同步
        trigger_immediate_sync(cluster, resource_type)
        if not ns_cache:
            trigger_immediate_sync(cluster, 'namespace')
        return JsonResponse({
            'resources': [],
            'namespaces': [],
            'syncing': True,
            'cluster_error': sync_err,
            'never_synced': cache_obj is None,
        })
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
        trigger_immediate_sync(cluster, 'deployment', wait=True)
        return JsonResponse({'success': True, 'resource': _serialize_resource(mgr, 'deployment', name, ns)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def deployment_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_deployment(name, ns)
        trigger_immediate_sync(cluster, 'deployment', wait=True)
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True, 'resource': _serialize_resource(mgr, 'deployment', name, ns)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def deployment_describe_api(request, pk, ns, name):
    """describe modal 用：基础信息 + conditions + events + 关联 pods 一次拿全"""
    _, mgr = _get_mgr(pk)
    try:
        return JsonResponse(mgr.describe_deployment(name, ns))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def deployment_revisions_api(request, pk, ns, name):
    """rollback modal 用：列出 ReplicaSet 历史"""
    _, mgr = _get_mgr(pk)
    try:
        return JsonResponse(mgr.list_deployment_revisions(name, ns))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def deployment_rollback(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body or '{}')
        revision = data.get('revision')
        if not revision:
            return JsonResponse({'error': 'revision is required'}, status=400)
        mgr.rollback_deployment(name, ns, revision)
        trigger_immediate_sync(cluster, 'deployment', wait=True)
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({
            'success': True,
            'resource': _serialize_resource(mgr, 'deployment', name, ns),
            'message': f'已回滚到 revision {revision}',
        })
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
        trigger_immediate_sync(cluster, 'statefulset', wait=True)
        return JsonResponse({'success': True, 'resource': _serialize_resource(mgr, 'statefulset', name, ns)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def statefulset_restart(request, pk, ns, name):
    cluster, mgr = _get_mgr(pk)
    try:
        mgr.restart_statefulset(name, ns)
        trigger_immediate_sync(cluster, 'statefulset', wait=True)
        trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True, 'resource': _serialize_resource(mgr, 'statefulset', name, ns)})
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
                # wait=True：阻塞等 cache 同步完成，保证前端紧跟的 silent load 不会拿到旧
                # 数据把刚改的 replicas/image 等覆盖回去
                trigger_immediate_sync(cluster, resource_type, wait=True)
                return JsonResponse(result)
            return JsonResponse(result, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ─── Generic Apply API（通用 YAML 创建/更新）──────────────────

@require_POST
def resource_validate_api(request, pk):
    """通用 yaml 校验：走 K8s server-side dry-run，给前端返回结构化诊断结果。

    所有资源类型共用同一个 endpoint，前端"验证语法"按钮调它。
    返回结构见 K8sResourceManager.validate_yaml。
    """
    _, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body or '{}')
        yaml_content = (data.get('yaml') or '').strip()
        if not yaml_content:
            return JsonResponse({'success': False, 'errors': [{'kind': '-', 'name': '-',
                'message': 'YAML 内容不能为空'}], 'warnings': [], 'docs': 0})
        return JsonResponse(mgr.validate_yaml(yaml_content))
    except Exception as e:
        return JsonResponse({'success': False, 'errors': [{'kind': '-', 'name': '-',
            'message': f'校验异常：{e}'}], 'warnings': [], 'docs': 0}, status=500)


@require_POST
def resource_apply_api(request, pk):
    """通用 apply YAML：从 YAML 内容自身解析 kind/name/namespace。

    给前端"+ 新建"按钮使用 —— 用户粘贴或修改 YAML 模板即可创建任意类型资源。
    底层复用 apply_yaml（已支持 create + replace + 改名等场景）。
    """
    cluster, mgr = _get_mgr(pk)
    try:
        data = json.loads(request.body)
        yaml_content = (data.get('yaml') or '').strip()
        if not yaml_content:
            return JsonResponse({'success': False, 'error': 'YAML 内容不能为空'}, status=400)
        result = mgr.apply_yaml(yaml_content)
        if result.get('success'):
            # 根据 actions 触发对应资源类型的立即同步：第一个 kind 用 wait=True 保证
            # 前端紧跟的 silent load 能拿到刚创建的资源；其他同 kind 异步避免串行
            # lock 累计阻塞太久（多 doc YAML 场景）
            seen_waited = set()
            for action in result.get('actions', []):
                kind = action.get('kind')
                if not kind:
                    continue
                trigger_immediate_sync(cluster, kind, wait=(kind not in seen_waited))
                seen_waited.add(kind)
            return JsonResponse(result)
        return JsonResponse(result, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Generic Delete API ──────────────────────────────────────

@require_POST
def resource_delete_api(request, pk, resource_type, name, ns=None):
    cluster, mgr = _get_mgr(pk)
    # force=1 时对 Pod 启用强制删除（跳过 30 秒优雅退出期，立即清除）
    force = request.GET.get('force') == '1' or request.POST.get('force') == '1'
    try:
        mgr.delete_resource(resource_type, name, ns, force=force)
        # wait=True：保证返回 HTTP 时 cache 已剔除该资源，前端 silent load 不会
        # 把刚 markRemoved 的项又拉回来（_pendingOps 的 remove op 也会兜底）
        trigger_immediate_sync(cluster, resource_type, wait=True)
        # 删 deployment / statefulset 等 controller 类资源时，关联 pod 也会被级联清，
        # 一并刷一次 pod cache
        if resource_type in ('deployment', 'statefulset', 'daemonset', 'job', 'cronjob'):
            trigger_immediate_sync(cluster, 'pod')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
