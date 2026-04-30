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
# 记录每个 cluster 最近一次 sync 是否失败：成功清空，失败留下原因。
# 列表 API 会把它透传给前端，让用户知道是 K8s 连不上 / kubeconfig 错 / 还是其他。
# 结构：{cluster_id: {'message': str, 'failed_at': iso_str, 'resource_type': str}}
_sync_last_error: Dict[int, dict] = {}


def get_sync_error(cluster_id):
    """供 view 查询某 cluster 最近一次同步是否有未恢复的错误"""
    return _sync_last_error.get(cluster_id)


def _describe_sync_error(exc):
    """把底层异常翻译成对运维有意义的中文一句话。

    K8s SDK / urllib3 / socket 抛出来的原始 message 很长且带堆栈信息，
    直接给用户看体验差；这里按特征字符串做粗分类。
    """
    msg = str(exc).lower()
    if 'kubeconfig' in msg or 'invalid kube-config' in msg:
        return f'kubeconfig 解析失败：{exc}'
    if 'unable to connect' in msg or 'connection refused' in msg or 'no route to host' in msg:
        return '无法连接到集群 API Server，请检查网络连通性或 kubeconfig 中的 server 地址'
    if 'timed out' in msg or 'timeout' in msg:
        return '连接集群超时，可能是网络抖动或 API Server 负载过高'
    if 'unauthorized' in msg or '401' in msg:
        return 'kubeconfig 凭证无效或已过期（401 Unauthorized）'
    if 'forbidden' in msg or '403' in msg:
        return '当前 kubeconfig 没有 list 权限（403 Forbidden）'
    if 'name or service not known' in msg or 'nodename nor servname' in msg:
        return '无法解析集群 API Server 的 DNS，请检查 kubeconfig 中的 server 地址'
    if 'certificate' in msg or 'x509' in msg or 'tls' in msg:
        return f'集群 TLS 证书校验失败：{exc}'
    return f'同步失败：{exc}'


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

        had_error = None  # 任意 kind 失败就记下，最后写入 _sync_last_error
        for resource_type in SYNC_ORDER:
            list_func = _list_func_for(cluster, resource_type)
            if not list_func:
                continue
            try:
                _sync_resource(cluster, resource_type, list_func)
            except Exception as e:
                logger.error(f'[Cluster {cluster.name}] Failed to sync {resource_type}: {e}')
                had_error = (resource_type, e)
                continue

        elapsed = time.time() - start_time
        if had_error is None:
            _sync_last_error.pop(cluster.pk, None)
        else:
            rt, exc = had_error
            _sync_last_error[cluster.pk] = {
                'resource_type': rt,
                'message': _describe_sync_error(exc),
                'failed_at': timezone.now().isoformat(),
            }
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
        # 容器层卡点：phase=Pending 时 K8s 会把具体原因写在 container_statuses[].state.waiting.reason
        # （ImagePullBackOff / CrashLoopBackOff / CreateContainerConfigError 等）。
        # 单独抽出来给前端用更醒目的 badge 展示，避免用户只看到 "Pending" 不知道卡哪了。
        status_reason = ''
        status_message = ''
        for cs in (status.container_statuses or []):
            st = cs.state
            if st and st.waiting and st.waiting.reason:
                status_reason = st.waiting.reason
                status_message = st.waiting.message or ''
                break
            if st and st.terminated and st.terminated.reason:
                status_reason = st.terminated.reason
                status_message = st.terminated.message or ''
                break
        # 容器没起 init container 也可能卡，扫一遍 init_container_statuses
        if not status_reason:
            for cs in (status.init_container_statuses or []):
                st = cs.state
                if st and st.waiting and st.waiting.reason and st.waiting.reason != 'PodInitializing':
                    status_reason = f'Init:{st.waiting.reason}'
                    status_message = st.waiting.message or ''
                    break
        base.update({
            'status_phase': 'Terminating' if is_terminating else (status.phase or 'Unknown'),
            'status_reason': status_reason,
            'status_message': status_message[:200] if status_message else '',
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
                # 单个资源同步成功不能简单清掉整个 cluster 的 error
                # （别的 kind 可能仍有问题），但这一类成功了就把它"忘掉"，
                # 让定时 sync 下一轮重新评估
                err = _sync_last_error.get(cluster_id)
                if err and err.get('resource_type') == resource_type:
                    _sync_last_error.pop(cluster_id, None)
                logger.info(f'[Cluster {cluster.name}] Immediate sync done for {resource_type}')
            except Exception as e:
                logger.error(f'[Cluster {cluster.name}] Immediate sync failed for {resource_type}: {e}')
                _sync_last_error[cluster_id] = {
                    'resource_type': resource_type,
                    'message': _describe_sync_error(e),
                    'failed_at': timezone.now().isoformat(),
                }

    thread = threading.Thread(target=_do_sync, daemon=True, name=f'ImmediateSync-{resource_type}')
    thread.start()
    if wait:
        # 阻塞等待最多 timeout 秒；若 lock 被定时 sync 占用太久则放弃，
        # 让定时 sync 自然兜底（避免 HTTP 请求卡死）
        thread.join(timeout=timeout)
