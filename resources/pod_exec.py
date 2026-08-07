"""Pod 直连终端（exec）的服务端会话管理。

为什么是「服务端持有长连接 + HTTP 轮询收发」而不是 WebSocket 直通：
本项目跑在 WSGI（runserver / gunicorn）上，没有装 channels/daphne，
WebSocket 直通要把整个部署改成 ASGI 全栈。而 K8s 的 exec 协议本身就是
WebSocket（SPDY 的后继），kubernetes 客户端用 websocket-client 已经实现好了。
所以这里让 Django 进程持有那条到 K8s 的 WebSocket，浏览器侧用短轮询收发字节，
换来的是零部署改造。代价是输入到回显有一个轮询周期的延迟。

安全上有三道约束，缺一不可：
  1. 路由挂在 /resources/<pk>/pods/... 下，且全部是 POST —— 会自动落到
     PermissionMiddleware 的 pod 模块 + edit 权限校验（shell 等价于完全控制）。
  2. 会话 token 与创建者 user_id 绑定，换个用户拿到 token 也用不了。
  3. 会话有空闲超时和总数上限，避免泄漏的会话把 K8s 连接和内存吃掉。
"""
import json
import secrets
import threading
import time

from django.http import JsonResponse
from kubernetes.stream import stream
from kubernetes.stream.ws_client import (
    ERROR_CHANNEL,
    RESIZE_CHANNEL,
    STDERR_CHANNEL,
    STDIN_CHANNEL,
    STDOUT_CHANNEL,
)

from clusters.k8s_client import k8s_pool

# 空闲多久没轮询就回收。终端前端每秒至少轮询一次，5 分钟没动静说明页面已经关了。
_IDLE_TIMEOUT = 300

# 全局会话上限。每个会话占一条到 K8s 的 WebSocket，不设上限等于给自己开 DoS。
_MAX_SESSIONS = 32

# 单次轮询最多等多久收数据。太短则空转、太长则占满 WSGI worker。
_POLL_WINDOW = 0.6

# 进入容器时依次尝试的 shell。distroless/scratch 镜像可能一个都没有，
# 那种情况下 K8s 会在 error channel 回报，前端照原样展示。
_SHELL_CMD = ['/bin/sh', '-c',
              'command -v bash >/dev/null 2>&1 && exec bash || exec sh']

_sessions = {}
_sessions_lock = threading.Lock()


class _Session:
    __slots__ = ('ws', 'user_id', 'cluster_id', 'namespace', 'pod',
                 'container', 'last_active', 'lock')

    def __init__(self, ws, user_id, cluster_id, namespace, pod, container):
        self.ws = ws
        self.user_id = user_id
        self.cluster_id = cluster_id
        self.namespace = namespace
        self.pod = pod
        self.container = container
        self.last_active = time.time()
        # WSClient 不是线程安全的，而轮询/resize/close 可能来自不同请求线程
        self.lock = threading.Lock()


def _reap_idle():
    """回收空闲会话。在每次新建会话时顺手做，不额外起后台线程。"""
    now = time.time()
    dead = [t for t, s in _sessions.items() if now - s.last_active > _IDLE_TIMEOUT]
    for token in dead:
        s = _sessions.pop(token, None)
        if s:
            try:
                s.ws.close()
            except Exception:
                pass


def _get(token, user):
    """按 token 取会话，并校验归属。找不到或不属于该用户一律当作不存在。"""
    if not token:
        return None
    s = _sessions.get(token)
    if s is None or s.user_id != user.id:
        return None
    return s


def open_session(request, cluster, namespace, pod_name):
    container = request.POST.get('container', '') or None

    with _sessions_lock:
        _reap_idle()
        if len(_sessions) >= _MAX_SESSIONS:
            return JsonResponse(
                {'error': f'终端会话数已达上限（{_MAX_SESSIONS}），请关闭其他终端后重试'},
                status=429)

    # 容器名用共享 client 读（普通 HTTP 请求，走连接池没问题）
    try:
        if not container:
            pod = k8s_pool.core_v1(cluster).read_namespaced_pod(
                pod_name, namespace, _request_timeout=5)
            if pod.spec.containers:
                container = pod.spec.containers[0].name
    except Exception as e:
        return JsonResponse({'error': f'读取容器列表失败：{e}'}, status=500)

    # exec 必须用独立 client：stream() 会临时替换 api_client.request，
    # 共享 client 会让其它线程的普通请求被误导到 WebSocket 上。详见
    # K8sClientPool.dedicated_core_v1 的说明。
    exec_core, exec_client = k8s_pool.dedicated_core_v1(cluster)
    try:
        ws = stream(
            exec_core.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            container=container,
            command=_SHELL_CMD,
            stdin=True, stdout=True, stderr=True, tty=True,
            _preload_content=False,
        )
    except Exception as e:
        return JsonResponse({'error': f'无法进入容器：{e}'}, status=500)
    finally:
        # 握手已完成，WebSocket 由 WSClient 自己持有，这里只回收线程池
        try:
            exec_client.close()
        except Exception:
            pass

    token = secrets.token_urlsafe(32)
    sess = _Session(ws, request.user.id, cluster.pk, namespace, pod_name, container)
    with _sessions_lock:
        _sessions[token] = sess

    return JsonResponse({'success': True, 'session': token, 'container': container})


def io_session(request, cluster, namespace, pod_name):
    """一次轮询：先把浏览器的按键写进去，再把容器的输出读出来。"""
    token = request.POST.get('session', '')
    sess = _get(token, request.user)
    if sess is None:
        return JsonResponse({'error': '终端会话不存在或已过期', 'closed': True}, status=404)

    data = request.POST.get('input', '')
    out, err, closed = [], '', False

    with sess.lock:
        sess.last_active = time.time()
        try:
            if data:
                sess.ws.write_channel(STDIN_CHANNEL, data)

            # 在窗口内轮着收，一有数据就立刻返回，避免无谓的整窗等待
            deadline = time.time() + _POLL_WINDOW
            while True:
                sess.ws.update(timeout=0.05)
                chunk = sess.ws.read_channel(STDOUT_CHANNEL)
                if chunk:
                    out.append(chunk)
                chunk = sess.ws.read_channel(STDERR_CHANNEL)
                if chunk:
                    out.append(chunk)
                if out or not sess.ws.is_open() or time.time() >= deadline:
                    break

            if not sess.ws.is_open():
                closed = True
                # error channel 里是 K8s 给的退出状态，正常退出也会有一条
                raw = sess.ws.read_channel(ERROR_CHANNEL)
                if raw:
                    try:
                        status = json.loads(raw)
                        if status.get('status') != 'Success':
                            err = status.get('message', '')
                    except (ValueError, AttributeError):
                        err = raw
        except Exception as e:
            closed = True
            err = str(e)

    if closed:
        with _sessions_lock:
            _sessions.pop(token, None)
        try:
            sess.ws.close()
        except Exception:
            pass

    return JsonResponse({'success': True, 'output': ''.join(out),
                         'closed': closed, 'error': err})


def resize_session(request, cluster, namespace, pod_name):
    sess = _get(request.POST.get('session', ''), request.user)
    if sess is None:
        return JsonResponse({'error': '终端会话不存在或已过期', 'closed': True}, status=404)
    try:
        cols = max(1, min(500, int(request.POST.get('cols', 80))))
        rows = max(1, min(200, int(request.POST.get('rows', 24))))
    except ValueError:
        return JsonResponse({'error': '窗口尺寸不合法'}, status=400)

    with sess.lock:
        sess.last_active = time.time()
        try:
            sess.ws.write_channel(
                RESIZE_CHANNEL, json.dumps({'Width': cols, 'Height': rows}))
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'success': True})


def close_session(request, cluster, namespace, pod_name):
    token = request.POST.get('session', '')
    sess = _get(token, request.user)
    if sess is None:
        # 幂等：已经没了就当关成功，前端不用处理这种竞态
        return JsonResponse({'success': True})
    with _sessions_lock:
        _sessions.pop(token, None)
    with sess.lock:
        try:
            sess.ws.close()
        except Exception:
            pass
    return JsonResponse({'success': True})
