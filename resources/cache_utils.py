from django.core.cache import cache

METRICS_CACHE_TTL = 60  # seconds


def metrics_cache_key(cluster_id):
    return f'k8s:{cluster_id}:metrics'


def cached_metrics(cluster_id, fetcher):
    """缓存集群 metrics 数据"""
    key = metrics_cache_key(cluster_id)
    result = cache.get(key)
    if result is not None:
        return result
    result = fetcher()
    cache.set(key, result, METRICS_CACHE_TTL)
    return result
