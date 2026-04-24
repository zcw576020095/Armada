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
        return cls._instance

    def get_client(self, cluster) -> client.ApiClient:
        cluster_id = cluster.id
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(kubeconfig_yaml)
            f.flush()
            loader = config.kube_config.KubeConfigLoader(
                config_dict=config.kube_config.KubeConfigMerger(f.name).config,
            )
            cfg = client.Configuration()
            loader.load_and_set(cfg)
            cfg.request_timeout = 5
            return client.ApiClient(configuration=cfg)

    def core_v1(self, cluster):
        return client.CoreV1Api(self.get_client(cluster))

    def apps_v1(self, cluster):
        return client.AppsV1Api(self.get_client(cluster))

    def networking_v1(self, cluster):
        return client.NetworkingV1Api(self.get_client(cluster))


k8s_pool = K8sClientPool()
