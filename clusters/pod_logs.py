"""共享的 Pod 日志获取逻辑 —— 给 clusters/resources 两个视图复用"""
from django.http import JsonResponse

from .k8s_client import k8s_pool


def fetch_pod_logs(cluster, namespace, pod_name, query_params):
    """从 K8s API 获取 Pod 日志，返回 JsonResponse。

    query_params: request.GET-like 对象，支持 .get(key, default)
    - container: 指定容器；为空时自动取 pod.spec.containers[0]
    - tail_lines: 末尾行数，默认 200
    - previous: 'true' 取上次重启前的日志
    """
    container = query_params.get('container', '')
    tail_lines = int(query_params.get('tail_lines', 200))
    previous = query_params.get('previous', 'false') == 'true'

    try:
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
        return JsonResponse({
            'success': True,
            'logs': logs or '',
            'container': container,
            'previous': previous,
        })
    except Exception as e:
        err_str = str(e)
        # 上次日志不存在 —— pod 从未重启过
        if previous and ('previous terminated' in err_str.lower()
                         or 'not found' in err_str.lower()
                         or 'previous' in err_str.lower()):
            return JsonResponse({
                'success': True,
                'logs': '',
                'container': container,
                'previous': previous,
                'no_previous': True,
            })
        return JsonResponse({'error': err_str}, status=500)
