import logging
import re
import threading
import yaml

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Cluster
from .k8s_client import k8s_pool
from .pod_logs import fetch_pod_logs
from .prometheus import PrometheusClient


logger = logging.getLogger(__name__)


def _parse_memory_bytes(mem_str: str) -> int:
    """Convert K8s memory string (Ki/Mi/Gi/bytes) to bytes."""
    if not mem_str:
        return 0
    m = re.match(r'^(\d+)\s*(Ki|Mi|Gi|Ti|K|M|G|T)?$', mem_str)
    if not m:
        return 0
    val = int(m.group(1))
    unit = m.group(2) or ''
    multipliers = {
        '': 1, 'K': 1000, 'M': 1000**2, 'G': 1000**3, 'T': 1000**4,
        'Ki': 1024, 'Mi': 1024**2, 'Gi': 1024**3, 'Ti': 1024**4,
    }
    return val * multipliers.get(unit, 1)


def _parse_memory(mem_str: str) -> str:
    """Convert K8s memory string to human-readable GB/MB."""
    bytes_val = _parse_memory_bytes(mem_str)
    if bytes_val == 0:
        return mem_str if (mem_str and not re.match(r'^\d', mem_str)) else '0'
    gb = bytes_val / (1024**3)
    if gb >= 1:
        return f'{gb:.0f} GB'
    mb = bytes_val / (1024**2)
    return f'{mb:.0f} MB'


def cluster_list(request):
    clusters = _visible_clusters(request.user)
    return render(request, 'clusters/list.html', {'clusters': clusters})


def _visible_clusters(user):
    """根据用户身份返回可见的集群：管理员看全部，普通用户只看自己有任一模块权限的集群"""
    from accounts.models import is_admin_user, UserModulePermission
    if is_admin_user(user):
        return Cluster.objects.all()
    visible_ids = UserModulePermission.objects.filter(user=user).values_list('cluster_id', flat=True).distinct()
    return Cluster.objects.filter(pk__in=visible_ids)


def cluster_add(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        display_name = request.POST.get('display_name', '').strip()
        description = request.POST.get('description', '').strip()
        prometheus_url = request.POST.get('prometheus_url', '').strip()
        kubeconfig_file = request.FILES.get('kubeconfig_file')
        kubeconfig_text = request.POST.get('kubeconfig_text', '').strip()

        kubeconfig_raw = ''
        if kubeconfig_file:
            kubeconfig_raw = kubeconfig_file.read().decode('utf-8')
        elif kubeconfig_text:
            kubeconfig_raw = kubeconfig_text

        if not name:
            messages.error(request, '集群名称不能为空')
            return render(request, 'clusters/add.html')
        if not kubeconfig_raw:
            messages.error(request, '请上传 Kubeconfig 文件或粘贴 YAML 内容')
            return render(request, 'clusters/add.html')

        try:
            parsed = yaml.safe_load(kubeconfig_raw)
            if not isinstance(parsed, dict) or 'clusters' not in parsed:
                messages.error(request, 'Kubeconfig 格式无效：缺少 clusters 字段')
                return render(request, 'clusters/add.html')
        except yaml.YAMLError as e:
            messages.error(request, f'YAML 解析失败：{e}')
            return render(request, 'clusters/add.html')

        if Cluster.objects.filter(name=name).exists():
            messages.error(request, f'集群名称 "{name}" 已存在')
            return render(request, 'clusters/add.html')

        api_server = ''
        try:
            api_server = parsed['clusters'][0]['cluster'].get('server', '')
        except (IndexError, KeyError, TypeError):
            pass

        cluster = Cluster(
            name=name,
            display_name=display_name or name,
            description=description,
            api_server=api_server,
            prometheus_url=prometheus_url,
        )
        cluster.set_kubeconfig(kubeconfig_raw)
        cluster.save()

        # Async refresh - don't block the redirect
        threading.Thread(target=_refresh_cluster_info, args=(cluster.pk,), daemon=True).start()

        messages.success(request, f'集群 "{cluster}" 导入成功，正在后台获取集群信息...')
        return redirect('clusters:list')

    return render(request, 'clusters/add.html')


def cluster_detail(request, pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    return render(request, 'clusters/detail.html', {'cluster': cluster})


def cluster_edit(request, pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    if request.method == 'POST':
        display_name = request.POST.get('display_name', '').strip()
        description = request.POST.get('description', '').strip()
        prometheus_url = request.POST.get('prometheus_url', '').strip()
        kubeconfig_file = request.FILES.get('kubeconfig_file')
        kubeconfig_text = request.POST.get('kubeconfig_text', '').strip()

        cluster.display_name = display_name or cluster.name
        cluster.description = description
        cluster.prometheus_url = prometheus_url

        kubeconfig_raw = ''
        if kubeconfig_file:
            kubeconfig_raw = kubeconfig_file.read().decode('utf-8')
        elif kubeconfig_text:
            kubeconfig_raw = kubeconfig_text

        if kubeconfig_raw:
            try:
                parsed = yaml.safe_load(kubeconfig_raw)
                if not isinstance(parsed, dict) or 'clusters' not in parsed:
                    messages.error(request, 'Kubeconfig 格式无效')
                    return render(request, 'clusters/edit.html', {'cluster': cluster})
            except yaml.YAMLError as e:
                messages.error(request, f'YAML 解析失败：{e}')
                return render(request, 'clusters/edit.html', {'cluster': cluster})

            api_server = ''
            try:
                api_server = parsed['clusters'][0]['cluster'].get('server', '')
            except (IndexError, KeyError, TypeError):
                pass
            cluster.api_server = api_server
            cluster.set_kubeconfig(kubeconfig_raw)

        cluster.save()

        threading.Thread(target=_refresh_cluster_info, args=(cluster.pk,), daemon=True).start()
        messages.success(request, f'集群 "{cluster}" 更新成功')
        return redirect('clusters:detail', pk=cluster.pk)

    return render(request, 'clusters/edit.html', {'cluster': cluster})


def cluster_nodes(request, pk):
    """Independent node management page."""
    cluster = get_object_or_404(Cluster, pk=pk)
    return render(request, 'clusters/nodes.html', {'cluster': cluster})


def cluster_nodes_api(request, pk):
    """AJAX endpoint: return nodes as JSON."""
    cluster = get_object_or_404(Cluster, pk=pk)
    nodes = []
    error = None
    try:
        core = k8s_pool.core_v1(cluster)
        node_list = core.list_node(_request_timeout=5)
        for n in node_list.items:
            info = n.status.node_info
            labels = n.metadata.labels or {}
            conditions = {c.type: c.status for c in n.status.conditions}
            capacity = n.status.capacity or {}
            gpu_count = capacity.get('nvidia.com/gpu', '0')
            gpu_model = labels.get('nvidia.com/gpu.product', '')
            is_gpu = gpu_count and gpu_count != '0'

            # Format GPU display: "A100 x 8" or "-"
            if is_gpu:
                model_short = gpu_model.split('-')[0] if gpu_model else 'GPU'
                gpu_display = f'{model_short} x {gpu_count}'
            else:
                gpu_display = '-'

            nodes.append({
                'name': n.metadata.name,
                'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
                'roles': ','.join(
                    k.replace('node-role.kubernetes.io/', '')
                    for k in labels
                    if k.startswith('node-role.kubernetes.io/')
                ) or 'worker',
                'node_type': gpu_model.split('-')[0] if gpu_model else ('GPU' if is_gpu else 'CPU'),
                'is_gpu': is_gpu,
                'k8s_version': info.kubelet_version,
                'os': info.os_image,
                'cpu_capacity': capacity.get('cpu', '0'),
                'memory_capacity': _parse_memory(capacity.get('memory', '0')),
                'gpu': gpu_display,
            })
    except Exception as e:
        error = str(e)

    # Stats
    ready_count = sum(1 for n in nodes if n['status'] == 'Ready')
    not_ready_count = len(nodes) - ready_count
    gpu_nodes = sum(1 for n in nodes if n['is_gpu'])

    return JsonResponse({
        'nodes': nodes,
        'error': error,
        'stats': {
            'total': len(nodes),
            'ready': ready_count,
            'not_ready': not_ready_count,
            'gpu_nodes': gpu_nodes,
        }
    })



@require_POST
def cluster_delete(request, pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    confirm_name = request.POST.get('confirm_name', '').strip()
    if confirm_name != cluster.name:
        messages.error(request, '集群名称不匹配，删除取消')
        return redirect('clusters:detail', pk=pk)

    k8s_pool.remove_client(cluster.id)
    cluster_name = str(cluster)
    cluster.delete()
    messages.success(request, f'集群 "{cluster_name}" 已删除')
    return redirect('clusters:list')


@require_POST
def cluster_refresh(request, pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    threading.Thread(target=_refresh_cluster_info, args=(cluster.pk,), daemon=True).start()
    messages.success(request, f'集群 "{cluster}" 正在后台刷新...')
    return redirect('clusters:detail', pk=pk)


@require_POST
def cluster_update_prometheus(request, pk):
    """Update Prometheus URL for a cluster."""
    cluster = get_object_or_404(Cluster, pk=pk)
    prometheus_url = request.POST.get('prometheus_url', '').strip()
    cluster.prometheus_url = prometheus_url
    cluster.save()
    if prometheus_url:
        messages.success(request, f'Prometheus 地址已更新为: {prometheus_url}')
    else:
        messages.info(request, 'Prometheus 地址已清空，将使用 Metrics Server')
    return redirect('clusters:detail', pk=pk)


def cluster_debug_prom(request, pk):
    """Debug: show raw Prometheus query results and K8s node names."""
    cluster = get_object_or_404(Cluster, pk=pk)
    result = {'prometheus_url': cluster.prometheus_url, 'k8s_nodes': [], 'prom_cpu_sample': [], 'prom_mem_sample': []}
    try:
        core = k8s_pool.core_v1(cluster)
        node_list = core.list_node(_request_timeout=5)
        result['k8s_nodes'] = [n.metadata.name for n in node_list.items]
    except Exception as e:
        result['k8s_error'] = str(e)

    if cluster.prometheus_url:
        prom = PrometheusClient(cluster.prometheus_url)
        result['prom_available'] = prom.is_available()
        # Get raw CPU sample
        raw = prom.query('sum by (instance, node, kubernetes_node) (rate(node_cpu_seconds_total{mode!="idle"}[5m]))')
        result['prom_cpu_sample'] = [{'metric': r['metric'], 'value': r['value'][1]} for r in raw[:3]]
        # Get raw mem sample
        raw2 = prom.query('node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes')
        result['prom_mem_sample'] = [{'metric': r['metric'], 'value': r['value'][1]} for r in raw2[:3]]
    return JsonResponse(result)


def cluster_select(request, pk):
    cluster = get_object_or_404(Cluster, pk=pk)
    request.session['active_cluster_id'] = cluster.id
    messages.success(request, f'已切换到集群 "{cluster}"')
    next_url = request.GET.get('next', '/')
    return redirect(next_url)


def node_detail(request, pk, node_name):
    """Node detail page - renders immediately, pods loaded via AJAX."""
    cluster = get_object_or_404(Cluster, pk=pk)
    can_edit = getattr(request, 'user_can_edit', True)
    return render(request, 'clusters/node_detail.html', {
        'cluster': cluster,
        'node_name': node_name,
        'can_edit': can_edit,
    })


def node_info_api(request, pk, node_name):
    """AJAX: return node info + pods as JSON."""
    cluster = get_object_or_404(Cluster, pk=pk)
    node_info = {}
    pods = []
    error = None
    try:
        core = k8s_pool.core_v1(cluster)
        node = core.read_node(node_name, _request_timeout=5)
        info = node.status.node_info
        labels = node.metadata.labels or {}
        conditions = {c.type: c.status for c in node.status.conditions}
        capacity = node.status.capacity or {}
        allocatable = node.status.allocatable or {}
        gpu_count = capacity.get('nvidia.com/gpu', '0')
        gpu_model = labels.get('nvidia.com/gpu.product', '')
        is_gpu = gpu_count and gpu_count != '0'

        node_info = {
            'name': node.metadata.name,
            'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
            'schedulable': node.spec.unschedulable is not True,
            'roles': ','.join(
                k.replace('node-role.kubernetes.io/', '')
                for k in labels if k.startswith('node-role.kubernetes.io/')
            ) or 'worker',
            'k8s_version': info.kubelet_version,
            'os': info.os_image,
            'kernel': info.kernel_version,
            'container_runtime': info.container_runtime_version,
            'arch': info.architecture,
            'cpu_capacity': capacity.get('cpu', '0'),
            'cpu_allocatable': allocatable.get('cpu', '0'),
            'memory_capacity': _parse_memory(capacity.get('memory', '0')),
            'memory_allocatable': _parse_memory(allocatable.get('memory', '0')),
            'gpu_count': gpu_count if is_gpu else '0',
            'gpu_model': gpu_model,
            'node_type': gpu_model.split('-')[0] if gpu_model else ('GPU' if is_gpu else 'CPU'),
            'is_gpu': is_gpu,
            'created': node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else '',
        }

        # Get pods on this node
        pod_list = core.list_pod_for_all_namespaces(
            field_selector=f'spec.nodeName={node_name}', _request_timeout=5
        )
        for p in pod_list.items:
            container_statuses = p.status.container_statuses or []
            ready = sum(1 for cs in container_statuses if cs.ready)
            total = len(p.spec.containers)
            restarts = sum(cs.restart_count for cs in container_statuses)

            pods.append({
                'name': p.metadata.name,
                'namespace': p.metadata.namespace,
                'status': p.status.phase,
                'ready': f'{ready}/{total}',
                'restarts': restarts,
                'ip': p.status.pod_ip or '-',
                'age': p.metadata.creation_timestamp.isoformat() if p.metadata.creation_timestamp else '',
            })
    except Exception as e:
        error = str(e)

    return JsonResponse({'node': node_info, 'pods': pods, 'error': error})


@require_POST
def node_cordon(request, pk, node_name):
    """Cordon a node (mark as unschedulable)."""
    cluster = get_object_or_404(Cluster, pk=pk)
    try:
        core = k8s_pool.core_v1(cluster)
        body = {"spec": {"unschedulable": True}}
        core.patch_node(node_name, body, _request_timeout=5)
        return JsonResponse({'success': True, 'message': f'节点 {node_name} 已设为不可调度 (Cordon)'})
    except Exception as e:
        return JsonResponse({'error': f'Cordon 失败：{e}'}, status=500)


@require_POST
def node_uncordon(request, pk, node_name):
    """Uncordon a node (mark as schedulable)."""
    cluster = get_object_or_404(Cluster, pk=pk)
    try:
        core = k8s_pool.core_v1(cluster)
        body = {"spec": {"unschedulable": None}}
        core.patch_node(node_name, body, _request_timeout=5)
        return JsonResponse({'success': True, 'message': f'节点 {node_name} 已恢复调度 (Uncordon)'})
    except Exception as e:
        return JsonResponse({'error': f'Uncordon 失败：{e}'}, status=500)


@require_POST
def node_drain(request, pk, node_name):
    """Drain a node: cordon + evict all pods."""
    cluster = get_object_or_404(Cluster, pk=pk)
    try:
        core = k8s_pool.core_v1(cluster)
        # Step 1: cordon
        core.patch_node(node_name, {"spec": {"unschedulable": True}}, _request_timeout=5)
        # Step 2: evict non-daemonset pods
        pod_list = core.list_pod_for_all_namespaces(
            field_selector=f'spec.nodeName={node_name}', _request_timeout=5
        )
        evicted = 0
        skipped = 0
        for p in pod_list.items:
            owner_refs = p.metadata.owner_references or []
            is_daemonset = any(ref.kind == 'DaemonSet' for ref in owner_refs)
            is_mirror = bool((p.metadata.annotations or {}).get('kubernetes.io/config.mirror'))
            if is_daemonset or is_mirror:
                skipped += 1
                continue
            try:
                eviction = {
                    "apiVersion": "policy/v1",
                    "kind": "Eviction",
                    "metadata": {
                        "name": p.metadata.name,
                        "namespace": p.metadata.namespace,
                    }
                }
                core.create_namespaced_pod_eviction(
                    p.metadata.name, p.metadata.namespace, eviction, _request_timeout=5
                )
                evicted += 1
            except Exception as e:
                logger.warning(
                    'Eviction failed for pod %s/%s on node %s: %s',
                    p.metadata.namespace, p.metadata.name, node_name, e
                )
                skipped += 1
        return JsonResponse({'success': True, 'message': f'节点 {node_name} 已 Drain，驱逐 {evicted} 个 Pod，跳过 {skipped} 个'})
    except Exception as e:
        return JsonResponse({'error': f'Drain 失败：{e}'}, status=500)


@require_POST
def node_delete(request, pk, node_name):
    """Delete node object from cluster."""
    cluster = get_object_or_404(Cluster, pk=pk)
    try:
        core = k8s_pool.core_v1(cluster)
        core.delete_node(node_name, _request_timeout=5)
        return JsonResponse({'success': True, 'message': f'节点 {node_name} 已从集群中移除'})
    except Exception as e:
        return JsonResponse({'error': f'移除节点失败：{e}'}, status=500)


def pod_logs_api(request, pk, namespace, pod_name):
    """Fetch logs for a specific pod."""
    cluster = get_object_or_404(Cluster, pk=pk)
    return fetch_pod_logs(cluster, namespace, pod_name, request.GET)


def _refresh_cluster_info(cluster_pk):
    """Fetch version and node info from cluster (runs in background thread)."""
    from django.db import connection
    try:
        cluster = Cluster.objects.get(pk=cluster_pk)
    except Cluster.DoesNotExist:
        return
    try:
        api_client = k8s_pool.refresh_client(cluster)
        version_api = api_client.call_api(
            '/version', 'GET', response_type='object',
            auth_settings=['BearerToken'], _return_http_data_only=True,
            _request_timeout=5
        )
        if isinstance(version_api, dict):
            cluster.k8s_version = version_api.get('gitVersion', '')

        core = k8s_pool.core_v1(cluster)
        node_list = core.list_node(_request_timeout=5)
        cluster.node_count = len(node_list.items)
        if node_list.items:
            os_set = set()
            for n in node_list.items:
                os_set.add(n.status.node_info.os_image)
            cluster.os_info = ' / '.join(sorted(os_set))
        cluster.status = 'online'
    except Exception:
        cluster.status = 'offline'
    cluster.save()
    connection.close()


def _parse_cpu_nano(cpu_str: str) -> float:
    """Convert K8s CPU string (e.g. '250m', '1', '2500n') to cores (float)."""
    if not cpu_str:
        return 0.0
    if cpu_str.endswith('n'):
        return int(cpu_str[:-1]) / 1e9
    if cpu_str.endswith('m'):
        return int(cpu_str[:-1]) / 1000.0
    return float(cpu_str)


def _fetch_metrics_data(cluster):
    """Fetch node capacity + metrics server data in parallel, return combined result."""
    from concurrent.futures import ThreadPoolExecutor
    from resources.cache_utils import cached_metrics

    def _do_fetch():
        core = k8s_pool.core_v1(cluster)
        node_cap = {}
        metrics_map = {}

        def fetch_nodes():
            node_list = core.list_node(_request_timeout=5)
            for n in node_list.items:
                cap = n.status.capacity or {}
                labels = n.metadata.labels or {}
                info = n.status.node_info
                conditions = {c.type: c.status for c in (n.status.conditions or [])}
                gpu_count = cap.get('nvidia.com/gpu', '0')
                is_gpu = gpu_count and gpu_count != '0'
                gpu_model = labels.get('nvidia.com/gpu.product', '')
                roles = ','.join(
                    k.replace('node-role.kubernetes.io/', '')
                    for k in labels if k.startswith('node-role.kubernetes.io/')
                ) or 'worker'
                node_cap[n.metadata.name] = {
                    'cpu_capacity': float(cap.get('cpu', '0')),
                    'mem_capacity': _parse_memory_bytes(cap.get('memory', '0')),
                    'is_gpu': is_gpu,
                    'gpu_count': int(gpu_count) if gpu_count and gpu_count != '0' else 0,
                    'gpu_model': gpu_model.split('-')[0] if gpu_model else '',
                    'status': 'Ready' if conditions.get('Ready') == 'True' else 'NotReady',
                    'roles': roles,
                    'container_runtime': info.container_runtime_version if info else '',
                    'os_image': info.os_image if info else '',
                    'kernel_version': info.kernel_version if info else '',
                    'kubelet_version': info.kubelet_version if info else '',
                    'arch': info.architecture if info else '',
                }

        def fetch_metrics():
            try:
                api_client = k8s_pool.get_client(cluster)
                metrics_raw = api_client.call_api(
                    '/apis/metrics.k8s.io/v1beta1/nodes', 'GET',
                    response_type='object', auth_settings=['BearerToken'],
                    _return_http_data_only=True, _request_timeout=5
                )
                metrics_items = metrics_raw.get('items', []) if isinstance(metrics_raw, dict) else []
                for item in metrics_items:
                    name = item.get('metadata', {}).get('name', '')
                    usage = item.get('usage', {})
                    metrics_map[name] = {
                        'cpu_used': _parse_cpu_nano(usage.get('cpu', '0')),
                        'mem_used': _parse_memory_bytes(usage.get('memory', '0')),
                    }
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(fetch_nodes)
            executor.submit(fetch_metrics)

        # Combine data
        nodes_data = []
        totals = {'cpu_capacity': 0.0, 'cpu_used': 0.0, 'mem_capacity': 0, 'mem_used': 0}
        data_source = 'metrics_server' if metrics_map else None

        for name, cap in node_cap.items():
            met = metrics_map.get(name, {'cpu_used': 0, 'mem_used': 0})
            cpu_cap = cap['cpu_capacity']
            cpu_used = met['cpu_used']
            mem_cap = cap['mem_capacity']
            mem_used = met['mem_used']

            totals['cpu_capacity'] += cpu_cap
            totals['cpu_used'] += cpu_used
            totals['mem_capacity'] += mem_cap
            totals['mem_used'] += mem_used

            nodes_data.append({
                'name': name,
                'is_gpu': cap['is_gpu'],
                'gpu_count': cap['gpu_count'],
                'gpu_model': cap.get('gpu_model', ''),
                'status': cap.get('status', 'Unknown'),
                'roles': cap.get('roles', 'worker'),
                'cpu_capacity': round(cpu_cap, 1),
                'cpu_used': round(cpu_used, 2),
                'cpu_percent': round(cpu_used / cpu_cap * 100, 1) if cpu_cap > 0 else 0,
                'mem_capacity_gb': round(mem_cap / (1024**3), 1),
                'mem_used_gb': round(mem_used / (1024**3), 1),
                'mem_percent': round(mem_used / mem_cap * 100, 1) if mem_cap > 0 else 0,
                'container_runtime': cap.get('container_runtime', ''),
                'os_image': cap.get('os_image', ''),
                'kernel_version': cap.get('kernel_version', ''),
                'kubelet_version': cap.get('kubelet_version', ''),
                'arch': cap.get('arch', ''),
            })

        nodes_data.sort(key=lambda x: x['name'])

        summary = {
            'cpu_capacity': round(totals['cpu_capacity'], 1),
            'cpu_used': round(totals['cpu_used'], 1),
            'cpu_percent': round(totals['cpu_used'] / totals['cpu_capacity'] * 100, 1) if totals['cpu_capacity'] > 0 else 0,
            'mem_capacity_gb': round(totals['mem_capacity'] / (1024**3), 1),
            'mem_used_gb': round(totals['mem_used'] / (1024**3), 1),
            'mem_percent': round(totals['mem_used'] / totals['mem_capacity'] * 100, 1) if totals['mem_capacity'] > 0 else 0,
        }

        return {
            'nodes': nodes_data,
            'summary': summary,
            'has_metrics': len(metrics_map) > 0,
            'data_source': data_source,
        }

    return cached_metrics(cluster.pk, _do_fetch)


def cluster_metrics_api(request, pk):
    """AJAX: return node-level CPU/memory/GPU metrics for dashboard charts."""
    cluster = get_object_or_404(Cluster, pk=pk)
    try:
        result = _fetch_metrics_data(cluster)
        result['error'] = None
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({
            'nodes': [],
            'summary': {'cpu_capacity': 0, 'cpu_used': 0, 'cpu_percent': 0,
                         'mem_capacity_gb': 0, 'mem_used_gb': 0, 'mem_percent': 0},
            'error': str(e),
            'has_metrics': False,
            'data_source': None,
        })
