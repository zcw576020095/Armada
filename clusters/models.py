import base64
import os

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


def _get_fernet():
    key = getattr(settings, 'KUBECONFIG_ENCRYPTION_KEY', None)
    if not key:
        raise ValueError("KUBECONFIG_ENCRYPTION_KEY not set in settings")
    return Fernet(key.encode() if isinstance(key, str) else key)


class Cluster(models.Model):
    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('unknown', '未知'),
    ]

    name = models.CharField('集群名称', max_length=128, unique=True)
    display_name = models.CharField('显示名称', max_length=128, blank=True)
    status = models.CharField('状态', max_length=16, choices=STATUS_CHOICES, default='unknown')
    k8s_version = models.CharField('K8s 版本', max_length=64, blank=True)
    os_info = models.CharField('系统信息', max_length=256, blank=True)
    api_server = models.CharField('API Server', max_length=512, blank=True)
    node_count = models.IntegerField('节点数', default=0)
    _kubeconfig_encrypted = models.BinaryField('Kubeconfig (加密)', editable=False)
    prometheus_url = models.CharField('Prometheus 地址', max_length=512, blank=True, help_text='例如: http://prometheus.monitoring:9090')
    description = models.TextField('描述', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '集群'
        verbose_name_plural = '集群'
        ordering = ['-created_at']

    def __str__(self):
        return self.display_name or self.name

    def set_kubeconfig(self, raw_yaml: str):
        f = _get_fernet()
        self._kubeconfig_encrypted = f.encrypt(raw_yaml.encode('utf-8'))

    def get_kubeconfig(self) -> str:
        f = _get_fernet()
        data = self._kubeconfig_encrypted
        if isinstance(data, memoryview):
            data = bytes(data)
        return f.decrypt(data).decode('utf-8')
