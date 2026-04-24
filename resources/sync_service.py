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
    from clusters.k8s_client import k8s_pool

    cluster_id = cluster.pk
    lock = _sync_locks.get(cluster_id)

    if not lock:
        return

    with lock:
        logger.info(f'[Cluster {cluster.name}] Starting sync cycle...')
        start_time = time.time()

        # 按优先级顺序同步
        resource_configs = [
            ('namespace', lambda: k8s_pool.core_v1(cluster).list_namespace(_request_timeout=30)),
            ('pod', lambda: k8s_pool.core_v1(cluster).list_pod_for_all_namespaces(_request_timeout=120)),
            ('deployment', lambda: k8s_pool.apps_v1(cluster).list_deployment_for_all_namespaces(_request_timeout=60)),
            ('service', lambda: k8s_pool.core_v1(cluster).list_service_for_all_namespaces(_request_timeout=60)),
            ('configmap', lambda: k8s_pool.core_v1(cluster).list_config_map_for_all_namespaces(_request_timeout=60)),
            ('secret', lambda: k8s_pool.core_v1(cluster).list_secret_for_all_namespaces(_request_timeout=60)),
            ('ingress', lambda: k8s_pool.networking_v1(cluster).list_ingress_for_all_namespaces(_request_timeout=60)),
            ('persistentvolumeclaim', lambda: k8s_pool.core_v1(cluster).list_persistent_volume_claim_for_all_namespaces(_request_timeout=60)),
            ('statefulset', lambda: k8s_pool.apps_v1(cluster).list_stateful_set_for_all_namespaces(_request_timeout=60)),
            ('daemonset', lambda: k8s_pool.apps_v1(cluster).list_daemon_set_for_all_namespaces(_request_timeout=60)),
        ]

        for resource_type, list_func in resource_configs:
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
        base['status'] = item.status.phase if item.status else '-'

    elif resource_type == 'pod':
        status = item.status or {}
        containers = item.spec.containers if item.spec else []
        ready = sum(1 for cs in (status.container_statuses or []) if cs.ready)
        restarts = sum(cs.restart_count for cs in (status.container_statuses or []))
        base.update({
            'status_phase': status.phase or 'Unknown',
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


def trigger_immediate_sync(cluster, resource_type):
    """触发指定资源类型的立即同步（用户操作后调用）"""
    from clusters.k8s_client import k8s_pool

    cluster_id = cluster.pk
    lock = _sync_locks.get(cluster_id)

    if not lock:
        logger.warning(f'No sync lock found for cluster {cluster.name}')
        return

    # 在后台线程中执行，避免阻塞用户请求
    def _do_sync():
        with lock:
            try:
                # 根据资源类型选择对应的 list 函数
                if resource_type == 'namespace':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_namespace(_request_timeout=30)
                elif resource_type == 'pod':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_pod_for_all_namespaces(_request_timeout=120)
                elif resource_type == 'deployment':
                    list_func = lambda: k8s_pool.apps_v1(cluster).list_deployment_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'service':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_service_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'statefulset':
                    list_func = lambda: k8s_pool.apps_v1(cluster).list_stateful_set_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'configmap':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_config_map_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'secret':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_secret_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'ingress':
                    list_func = lambda: k8s_pool.networking_v1(cluster).list_ingress_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'persistentvolumeclaim':
                    list_func = lambda: k8s_pool.core_v1(cluster).list_persistent_volume_claim_for_all_namespaces(_request_timeout=60)
                elif resource_type == 'daemonset':
                    list_func = lambda: k8s_pool.apps_v1(cluster).list_daemon_set_for_all_namespaces(_request_timeout=60)
                else:
                    logger.warning(f'Unknown resource type: {resource_type}')
                    return

                _sync_resource(cluster, resource_type, list_func)
                logger.info(f'[Cluster {cluster.name}] Immediate sync triggered for {resource_type}')
            except Exception as e:
                logger.error(f'[Cluster {cluster.name}] Immediate sync failed for {resource_type}: {e}')

    thread = threading.Thread(target=_do_sync, daemon=True, name=f'ImmediateSync-{resource_type}')
    thread.start()
