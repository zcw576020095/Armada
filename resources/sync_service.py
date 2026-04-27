"""
K8s 资源同步服务 - 定时从 K8s API 拉取数据并存入数据库

核心思路：
1. 后台线程定时（30-60秒）同步各资源类型
2. 串行同步避免并发打爆 K8s API
3. 只存储前端需要的字段（轻量级 JSON）
4. 数据库查询比 K8s API 快 100+ 倍
"""
import threading
import time
import logging
from typing import Dict
from django.utils import timezone

logger = logging.getLogger(__name__)

# 全局同步线程管理
_sync_threads: Dict[int, threading.Thread] = {}
_sync_locks: Dict[int, threading.Lock] = {}


def _list_func_for(cluster, resource_type):
    """根据资源类型返回对应的 K8s list 函数（调用时延迟解析 k8s_pool 和 cluster）。"""
    from clusters.k8s_client import k8s_pool

    # (api_attr, list_method, timeout)
    mapping = {
        'namespace':             ('core_v1',       'list_namespace',                                30),
        'pod':                   ('core_v1',       'list_pod_for_all_namespaces',                  120),
        'deployment':            ('apps_v1',       'list_deployment_for_all_namespaces',            60),
        'statefulset':           ('apps_v1',       'list_stateful_set_for_all_namespaces',          60),
        'daemonset':             ('apps_v1',       'list_daemon_set_for_all_namespaces',            60),
        'service':               ('core_v1',       'list_service_for_all_namespaces',               60),
        'configmap':             ('core_v1',       'list_config_map_for_all_namespaces',            60),
        'secret':                ('core_v1',       'list_secret_for_all_namespaces',                60),
        'ingress':               ('networking_v1', 'list_ingress_for_all_namespaces',               60),
        'persistentvolumeclaim': ('core_v1',       'list_persistent_volume_claim_for_all_namespaces', 60),
    }
    entry = mapping.get(resource_type)
    if not entry:
        return None
    api_attr, method_name, timeout = entry

    def _call():
        api = getattr(k8s_pool, api_attr)(cluster)
        return getattr(api, method_name)(_request_timeout=timeout)

    return _call


# 同步优先级顺序（先同步的会先被用户看到）
SYNC_ORDER = [
    'namespace', 'pod', 'deployment', 'service',
    'configmap', 'secret', 'ingress',
    'persistentvolumeclaim', 'statefulset', 'daemonset',
]


def start_sync_for_cluster(cluster):
    """为集群启动后台同步线程"""
    cluster_id = cluster.pk

    if cluster_id in _sync_threads and _sync_threads[cluster_id].is_alive():
        logger.warning(f'Sync thread for cluster {cluster.name} already running')
        return

    _sync_locks[cluster_id] = threading.Lock()
    thread = threading.Thread(
        target=_sync_loop,
        args=(cluster,),
        daemon=True,
        name=f'K8sSync-{cluster.name}'
    )
    _sync_threads[cluster_id] = thread
    thread.start()
    logger.info(f'Started sync thread for cluster {cluster.name}')


def _sync_loop(cluster):
    """同步循环：立即执行一次，然后每 60 秒执行一次"""
    cluster_id = cluster.pk

    # 首次立即同步
    _sync_all_resources(cluster)

    # 定时同步
    while True:
        try:
            time.sleep(60)  # 60 秒间隔
            _sync_all_resources(cluster)
        except Exception as e:
            logger.error(f'[Cluster {cluster.name}] Sync loop error: {e}', exc_info=True)
            time.sleep(10)


def _sync_all_resources(cluster):
    """同步所有资源类型（串行执行）"""
    cluster_id = cluster.pk
    lock = _sync_locks.get(cluster_id)

    if not lock:
        return

    with lock:
        logger.info(f'[Cluster {cluster.name}] Starting sync cycle...')
        start_time = time.time()

        for resource_type in SYNC_ORDER:
            list_func = _list_func_for(cluster, resource_type)
            if not list_func:
                continue
            try:
                _sync_resource(cluster, resource_type, list_func)
            except Exception as e:
                logger.error(f'[Cluster {cluster.name}] Failed to sync {resource_type}: {e}')
                continue

        elapsed = time.time() - start_time
        logger.info(f'[Cluster {cluster.name}] Sync cycle completed in {elapsed:.1f}s')


def _sync_resource(cluster, resource_type, list_func):
    """同步单个资源类型"""
    from resources.models import K8sResourceCache

    start = time.time()

    # 调用 K8s API
    result = list_func()
    items = result.items

    # 序列化为轻量级 dict
    serialized = []
    for item in items:
        try:
            data = _serialize_item(resource_type, item)
            serialized.append(data)
        except Exception as e:
            logger.warning(f'Failed to serialize {resource_type} {item.metadata.name}: {e}')
            continue

    # 更新数据库
    K8sResourceCache.objects.update_or_create(
        cluster_id=cluster.pk,
        resource_type=resource_type,
        namespace='',  # 全量数据
        defaults={
            'data': serialized,
            'synced_at': timezone.now(),
        }
    )

    elapsed = time.time() - start
    logger.info(f'[{resource_type}] Synced {len(serialized)} items in {elapsed:.1f}s')


def _serialize_item(resource_type, item):
    """将 K8s 对象序列化为轻量级 dict"""

    def _ts(obj):
        ts = getattr(obj.metadata, 'creation_timestamp', None)
        return ts.strftime('%Y-%m-%d %H:%M') if ts else '-'

    def _age(obj):
        """计算资源运行时长，类似 kubectl 的 Age 字段"""
        ts = getattr(obj.metadata, 'creation_timestamp', None)
        if not ts:
            return '-'
        from django.utils import timezone as tz
        delta = tz.now() - ts
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return '0s'
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        if days > 0:
            return f'{days}d{hours}h' if hours > 0 else f'{days}d'
        if hours > 0:
            return f'{hours}h{minutes}m' if minutes > 0 else f'{hours}h'
        if minutes > 0:
            return f'{minutes}m'
        return f'{total_seconds}s'

    base = {
        'name': item.metadata.name,
        'namespace': getattr(item.metadata, 'namespace', None),
        'created': _ts(item),
        'age': _age(item),
    }

    if resource_type == 'namespace':
        # Namespace 被删除时 Terminating 状态可能持续很久（finalizer 清理所有资源）
        is_terminating = getattr(item.metadata, 'deletion_timestamp', None) is not None
        if is_terminating:
            base['status'] = 'Terminating'
        else:
            base['status'] = item.status.phase if item.status else '-'

    elif resource_type == 'pod':
        status = item.status or {}
        containers = item.spec.containers if item.spec else []
        ready = sum(1 for cs in (status.container_statuses or []) if cs.ready)
        restarts = sum(cs.restart_count for cs in (status.container_statuses or []))
        # Pod 被删除但仍在优雅退出期时，metadata.deletion_timestamp 有值，
        # 此时 status.phase 可能还是 Running/Pending，但实际已在终止
        is_terminating = getattr(item.metadata, 'deletion_timestamp', None) is not None
        base.update({
            'status_phase': 'Terminating' if is_terminating else (status.phase or 'Unknown'),
            'ready_str': f'{ready}/{len(containers)}',
            'restarts': restarts,
            'node': item.spec.node_name or '-',
            'ip': status.pod_ip or '-',
        })

    elif resource_type == 'deployment':
        spec = item.spec or {}
        status = item.status or {}
        base.update({
            'replicas': spec.replicas or 0,
            'ready_replicas': status.ready_replicas or 0,
            'available': status.available_replicas or 0,
            'image': (spec.template.spec.containers[0].image
                      if spec.template and spec.template.spec and spec.template.spec.containers
                      else '-'),
        })

    elif resource_type == 'statefulset':
        spec = item.spec or {}
        status = item.status or {}
        base.update({
            'replicas': spec.replicas or 0,
            'ready_replicas': status.ready_replicas or 0,
            'image': (spec.template.spec.containers[0].image
                      if spec.template and spec.template.spec and spec.template.spec.containers
                      else '-'),
        })

    elif resource_type == 'daemonset':
        status = item.status or {}
        base.update({
            'desired': status.desired_number_scheduled or 0,
            'current': status.current_number_scheduled or 0,
            'ready': status.number_ready or 0,
            'image': (item.spec.template.spec.containers[0].image
                      if item.spec and item.spec.template and item.spec.template.spec
                      and item.spec.template.spec.containers else '-'),
        })

    elif resource_type == 'service':
        spec = item.spec or {}
        ports = ', '.join(
            f"{p.port}" + (f":{p.node_port}" if p.node_port else "") + f"/{p.protocol}"
            for p in (spec.ports or [])
        )
        base.update({
            'type': spec.type or '-',
            'cluster_ip': spec.cluster_ip or '-',
            'ports': ports or '-',
        })

    elif resource_type == 'configmap':
        data = item.data or {}
        base.update({
            'key_count': len(data),
            'keys': list(data.keys()),
        })

    elif resource_type == 'secret':
        data = item.data or {}
        base.update({
            'type': item.type or 'Opaque',
            'key_count': len(data),
            'keys': list(data.keys()),
        })

    elif resource_type == 'ingress':
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
        base.update({
            'rules_str': '; '.join(rules) if rules else '-',
            'class_name': spec.ingress_class_name or '-',
        })

    elif resource_type == 'persistentvolumeclaim':
        spec = item.spec or {}
        status = item.status or {}
        storage = '-'
        if spec.resources and spec.resources.requests:
            storage = spec.resources.requests.get('storage', '-')
        base.update({
            'status_phase': status.phase or 'Unknown',
            'storage': storage,
            'access_modes': ', '.join(spec.access_modes or []),
            'storage_class': spec.storage_class_name or '-',
        })

    return base


def stop_sync_for_cluster(cluster_id):
    """停止集群的同步线程（通过删除锁让线程自然退出）"""
    if cluster_id in _sync_locks:
        del _sync_locks[cluster_id]
    if cluster_id in _sync_threads:
        del _sync_threads[cluster_id]
    logger.info(f'Stopped sync for cluster {cluster_id}')


def trigger_immediate_sync(cluster, resource_type, wait=False, timeout=5):
    """触发指定资源类型的立即同步（用户操作后调用）。

    wait=False（默认）: 异步启动线程，立即返回 —— 适合 scale/restart 等读取频繁的场景
    wait=True: 阻塞等待同步完成（最多 timeout 秒）—— 适合 create/delete 等关键写操作，
              确保前端紧接着的 list API 能拿到最新数据，无需等 60s 周期或乐观更新兜底
    """
    cluster_id = cluster.pk
    lock = _sync_locks.get(cluster_id)

    if not lock:
        logger.warning(f'No sync lock found for cluster {cluster.name}')
        return

    list_func = _list_func_for(cluster, resource_type)
    if not list_func:
        logger.warning(f'Unknown resource type: {resource_type}')
        return

    def _do_sync():
        with lock:
            try:
                _sync_resource(cluster, resource_type, list_func)
                logger.info(f'[Cluster {cluster.name}] Immediate sync done for {resource_type}')
            except Exception as e:
                logger.error(f'[Cluster {cluster.name}] Immediate sync failed for {resource_type}: {e}')

    thread = threading.Thread(target=_do_sync, daemon=True, name=f'ImmediateSync-{resource_type}')
    thread.start()
    if wait:
        # 阻塞等待最多 timeout 秒；若 lock 被定时 sync 占用太久则放弃，
        # 让定时 sync 自然兜底（避免 HTTP 请求卡死）
        thread.join(timeout=timeout)
