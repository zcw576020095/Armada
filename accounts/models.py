from django.contrib.auth.models import User
from django.db import models
from clusters.models import Cluster


class UserProfile(models.Model):
    """用户扩展信息"""
    ROLE_CHOICES = [
        ('admin', '管理员'),
        ('user', '普通用户'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField('角色', max_length=16, choices=ROLE_CHOICES, default='user')
    real_name = models.CharField('姓名', max_length=64, blank=True)
    phone = models.CharField('手机号', max_length=32, blank=True)
    department = models.CharField('部门', max_length=128, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    def is_admin(self):
        return self.role == 'admin'


class UserModulePermission(models.Model):
    """用户模块权限 - 控制用户对每个功能模块的访问"""

    # 所有可授权的模块
    MODULE_CHOICES = [
        ('dashboard', '仪表盘'),
        ('cluster', '集群管理'),
        ('node', '节点管理'),
        ('namespace', '命名空间'),
        ('deployment', 'Deployment'),
        ('statefulset', 'StatefulSet'),
        ('daemonset', 'DaemonSet'),
        ('pod', 'Pod'),
        ('service', 'Service'),
        ('ingress', 'Ingress'),
        ('configmap', 'ConfigMap'),
        ('secret', 'Secret'),
        ('pvc', 'PVC'),
    ]

    PERMISSION_CHOICES = [
        ('view', '查看'),
        ('edit', '编辑'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_permissions')
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name='module_permissions')
    module = models.CharField('模块', max_length=32, choices=MODULE_CHOICES)
    permission = models.CharField('权限', max_length=16, choices=PERMISSION_CHOICES, default='view')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '用户模块权限'
        verbose_name_plural = '用户模块权限'
        unique_together = ['user', 'cluster', 'module']
        ordering = ['user', 'cluster', 'module']

    def __str__(self):
        return f"{self.user.username} - {self.cluster} - {self.get_module_display()}: {self.get_permission_display()}"

    def can_edit(self):
        return self.permission == 'edit'


# 保留旧模型兼容迁移，但不再使用
class UserClusterPermission(models.Model):
    """[已废弃] 旧权限模型"""
    RESOURCE_TYPES = [
        ('*', '所有资源'),
        ('namespace', 'Namespace'),
        ('node', 'Node'),
        ('deployment', 'Deployment'),
        ('statefulset', 'StatefulSet'),
        ('daemonset', 'DaemonSet'),
        ('pod', 'Pod'),
        ('service', 'Service'),
        ('ingress', 'Ingress'),
        ('configmap', 'ConfigMap'),
        ('secret', 'Secret'),
        ('persistentvolumeclaim', 'PVC'),
    ]

    PERMISSION_CHOICES = [
        ('view', '查看'),
        ('edit', '编辑'),
        ('delete', '删除'),
        ('full', '完全控制'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cluster_permissions')
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name='user_permissions')
    namespace = models.CharField('命名空间', max_length=128, blank=True)
    resource_type = models.CharField('资源类型', max_length=32, choices=RESOURCE_TYPES, default='*')
    permission = models.CharField('权限', max_length=16, choices=PERMISSION_CHOICES, default='view')
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '用户集群权限(旧)'
        verbose_name_plural = '用户集群权限(旧)'
        unique_together = ['user', 'cluster', 'namespace', 'resource_type']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.cluster}"

    def allows_view(self):
        return self.permission in ('view', 'edit', 'delete', 'full')

    def allows_edit(self):
        return self.permission in ('edit', 'delete', 'full')

    def allows_delete(self):
        return self.permission in ('delete', 'full')
