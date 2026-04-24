from django.db import models
from django.utils import timezone


class K8sResourceCache(models.Model):
    """K8s 资源缓存表 - 存储序列化后的资源列表"""
    cluster_id = models.IntegerField(db_index=True)
    resource_type = models.CharField(max_length=50, db_index=True)
    namespace = models.CharField(max_length=255, default='', db_index=True)
    data = models.JSONField()
    synced_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'k8s_resource_cache'
        unique_together = [['cluster_id', 'resource_type', 'namespace']]

    def __str__(self):
        return f'{self.cluster_id}:{self.resource_type}:{self.namespace or "all"}'
