import os
import tempfile
import threading

from kubernetes import client, config


class K8sClientPool:
    """Singleton pool that caches kubernetes API clients per cluster."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._clients = {}
                    cls._instance._load_lock = threading.Lock()
        return cls._instance

    def get_client(self, cluster) -> client.ApiClient:
        cluster_id = cluster.id
        # 快路径：已缓存直接返回
        if cluster_id in self._clients:
            return self._clients[cluster_id]

        # 慢路径：加锁避免多线程重复加载（double-check）
        with self._load_lock:
            if cluster_id in self._clients:
                return self._clients[cluster_id]
            kubeconfig_yaml = cluster.get_kubeconfig()
            api_client = self._load_client(kubeconfig_yaml)
            self._clients[cluster_id] = api_client
            return api_client

    def remove_client(self, cluster_id: int):
        self._clients.pop(cluster_id, None)

    def refresh_client(self, cluster):
        self.remove_client(cluster.id)
        return self.get_client(cluster)

    def _load_client(self, kubeconfig_yaml: str) -> client.ApiClient:
        # 临时写文件仅用于 KubeConfigMerger 读取，加载完立刻删除
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_yaml)
                f.flush()
                tmp_path = f.name
            loader = config.kube_config.KubeConfigLoader(
                config_dict=config.kube_config.KubeConfigMerger(tmp_path).config,
            )
            cfg = client.Configuration()
            loader.load_and_set(cfg)
            cfg.request_timeout = 5
            return client.ApiClient(configuration=cfg)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def dedicated_core_v1(self, cluster):
        """给 exec/attach 这类 WebSocket 调用用的**独立** CoreV1Api，不走缓存。

        必须独立，否则会打断其它线程的普通请求：`kubernetes.stream.stream()`
        的实现（stream/stream.py）会把 `api_client.request` 临时替换成
        WebSocket 版本，调用结束再还原。池里的 ApiClient 是跨线程共享的，
        在那个替换窗口内，后台同步线程发出的 list 请求会被送到 WebSocket
        实现上，报 `Handshake status 200 OK`。实测并发下 60 次 list 有 3 次
        因此失败。

        调用方拿到后应在握手完成（拿到 WSClient）后 close() 掉这个 client：
        WebSocket 由 WSClient 自己持有，close() 只回收 ApiClient 的线程池，
        不影响已建立的连接。
        """
        api_client = self._load_client(cluster.get_kubeconfig())
        return client.CoreV1Api(api_client), api_client

    def core_v1(self, cluster):
        return client.CoreV1Api(self.get_client(cluster))

    def apps_v1(self, cluster):
        return client.AppsV1Api(self.get_client(cluster))

    def networking_v1(self, cluster):
        return client.NetworkingV1Api(self.get_client(cluster))


k8s_pool = K8sClientPool()
