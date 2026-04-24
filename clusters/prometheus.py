import requests


class PrometheusClient:
    """Query Prometheus for cluster metrics."""

    def __init__(self, base_url: str, timeout: int = 5):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def query(self, promql: str) -> list:
        """Execute instant query, return list of {metric, value} dicts."""
        try:
            resp = requests.get(
                f'{self.base_url}/api/v1/query',
                params={'query': promql},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('status') == 'success':
                return data.get('data', {}).get('result', [])
        except Exception:
            pass
        return []

    def is_available(self) -> bool:
        try:
            resp = requests.get(
                f'{self.base_url}/api/v1/status/buildinfo',
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _extract_node(self, metric: dict) -> str:
        """Extract node name/IP from Prometheus metric labels."""
        # Priority: node > kubernetes_node > nodename > instance (strip port)
        for key in ('node', 'kubernetes_node', 'nodename'):
            val = metric.get(key)
            if val:
                return val
        instance = metric.get('instance', '')
        if instance:
            return instance.split(':')[0]
        return ''

    def get_node_cpu_usage(self) -> dict:
        """Return {node_name: cpu_cores_used}."""
        results = self.query(
            'sum by (node) ('
            '  rate(node_cpu_seconds_total{mode!="idle"}[5m])'
            ')'
        )
        if not results:
            # Fallback: group by instance
            results = self.query(
                'sum by (instance) ('
                '  rate(node_cpu_seconds_total{mode!="idle"}[5m])'
                ')'
            )
        out = {}
        for r in results:
            node = self._extract_node(r['metric'])
            if node:
                out[node] = round(float(r['value'][1]), 2)
        return out

    def get_node_memory_usage(self) -> dict:
        """Return {node_name: memory_bytes_used}."""
        results = self.query(
            'sum by (node) (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)'
        )
        if not results:
            results = self.query(
                'sum by (instance) (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)'
            )
        out = {}
        for r in results:
            node = self._extract_node(r['metric'])
            if node:
                out[node] = int(float(r['value'][1]))
        return out

    def get_node_load(self) -> dict:
        """Return {node_name: load1}."""
        results = self.query('sum by (node) (node_load1)')
        if not results:
            results = self.query('sum by (instance) (node_load1)')
        out = {}
        for r in results:
            node = self._extract_node(r['metric'])
            if node:
                out[node] = round(float(r['value'][1]), 2)
        return out

    def get_node_disk_usage(self) -> dict:
        """Return {node_name: {used_gb, total_gb, percent}}."""
        # Total
        total_results = self.query(
            'sum by (node) (node_filesystem_size_bytes{mountpoint="/",fstype!="tmpfs"})'
        )
        if not total_results:
            total_results = self.query(
                'sum by (instance) (node_filesystem_size_bytes{mountpoint="/",fstype!="tmpfs"})'
            )
        # Available
        avail_results = self.query(
            'sum by (node) (node_filesystem_avail_bytes{mountpoint="/",fstype!="tmpfs"})'
        )
        if not avail_results:
            avail_results = self.query(
                'sum by (instance) (node_filesystem_avail_bytes{mountpoint="/",fstype!="tmpfs"})'
            )

        total_map = {}
        for r in total_results:
            node = self._extract_node(r['metric'])
            if node:
                total_map[node] = float(r['value'][1])

        out = {}
        for r in avail_results:
            node = self._extract_node(r['metric'])
            if node and node in total_map:
                total_bytes = total_map[node]
                avail_bytes = float(r['value'][1])
                used_bytes = total_bytes - avail_bytes
                out[node] = {
                    'used_gb': round(used_bytes / (1024**3), 1),
                    'total_gb': round(total_bytes / (1024**3), 1),
                    'percent': round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0,
                }
        return out

    def get_gpu_utilization(self) -> dict:
        """Return {node_name: [{gpu_index, utilization, model}]}."""
        # Try DCGM exporter first
        results = self.query('DCGM_FI_DEV_GPU_UTIL')
        if not results:
            # Try nvidia_smi_exporter format
            results = self.query('nvidia_smi_utilization_gpu_ratio * 100')

        out = {}
        for r in results:
            metric = r['metric']
            node = metric.get('node') or metric.get('Hostname') or metric.get('instance', '').split(':')[0]
            if not node:
                continue
            if node not in out:
                out[node] = []
            out[node].append({
                'gpu_index': metric.get('gpu', metric.get('minor_number', '0')),
                'utilization': round(float(r['value'][1]), 1),
                'model': metric.get('modelName', metric.get('gpu_model', '')),
            })
        return out

    def get_gpu_memory(self) -> dict:
        """Return {node_name: [{gpu_index, used_mb, total_mb, model}]}."""
        # DCGM format
        used_results = self.query('DCGM_FI_DEV_FB_USED')
        total_results = self.query('DCGM_FI_DEV_FB_TOTAL')

        if not used_results:
            # nvidia_smi format (bytes)
            used_results = self.query('nvidia_smi_memory_used_bytes')
            total_results = self.query('nvidia_smi_memory_total_bytes')

        used_map = {}
        for r in used_results:
            metric = r['metric']
            node = metric.get('node') or metric.get('Hostname') or metric.get('instance', '').split(':')[0]
            gpu = metric.get('gpu', metric.get('minor_number', '0'))
            key = f'{node}:{gpu}'
            val = float(r['value'][1])
            # DCGM reports in MiB, nvidia_smi in bytes
            used_map[key] = {
                'node': node, 'gpu': gpu,
                'used_mb': val if val < 1e6 else round(val / (1024**2)),
                'model': metric.get('modelName', metric.get('gpu_model', '')),
            }

        total_map = {}
        for r in total_results:
            metric = r['metric']
            node = metric.get('node') or metric.get('Hostname') or metric.get('instance', '').split(':')[0]
            gpu = metric.get('gpu', metric.get('minor_number', '0'))
            key = f'{node}:{gpu}'
            val = float(r['value'][1])
            total_map[key] = val if val < 1e6 else round(val / (1024**2))

        out = {}
        for key, info in used_map.items():
            node = info['node']
            if node not in out:
                out[node] = []
            out[node].append({
                'gpu_index': info['gpu'],
                'used_mb': round(info['used_mb']),
                'total_mb': round(total_map.get(key, 0)),
                'model': info['model'],
            })
        return out
