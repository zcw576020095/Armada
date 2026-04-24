from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import UserProfile, UserModulePermission


# 不需要登录的路径
LOGIN_EXEMPT_URLS = [
    '/accounts/login/',
    '/admin/',
    '/static/',
]

# URL 路径 -> 模块映射
# 格式: (路径前缀, 模块名)
MODULE_MAPPING = [
    # resources 模块
    ('/resources/{pk}/namespaces/', 'namespace'),
    ('/resources/{pk}/deployments/', 'deployment'),
    ('/resources/{pk}/statefulsets/', 'statefulset'),
    ('/resources/{pk}/daemonsets/', 'daemonset'),
    ('/resources/{pk}/pods/', 'pod'),
    ('/resources/{pk}/services/', 'service'),
    ('/resources/{pk}/ingresses/', 'ingress'),
    ('/resources/{pk}/configmaps/', 'configmap'),
    ('/resources/{pk}/secrets/', 'secret'),
    ('/resources/{pk}/pvcs/', 'pvc'),
    # yaml/delete 通用 API
    ('/resources/{pk}/yaml/namespace', 'namespace'),
    ('/resources/{pk}/yaml/deployment', 'deployment'),
    ('/resources/{pk}/yaml/statefulset', 'statefulset'),
    ('/resources/{pk}/yaml/daemonset', 'daemonset'),
    ('/resources/{pk}/yaml/pod', 'pod'),
    ('/resources/{pk}/yaml/service', 'service'),
    ('/resources/{pk}/yaml/ingress', 'ingress'),
    ('/resources/{pk}/yaml/configmap', 'configmap'),
    ('/resources/{pk}/yaml/secret', 'secret'),
    ('/resources/{pk}/yaml/persistentvolumeclaim', 'pvc'),
    ('/resources/{pk}/delete/namespace', 'namespace'),
    ('/resources/{pk}/delete/deployment', 'deployment'),
    ('/resources/{pk}/delete/statefulset', 'statefulset'),
    ('/resources/{pk}/delete/daemonset', 'daemonset'),
    ('/resources/{pk}/delete/pod', 'pod'),
    ('/resources/{pk}/delete/service', 'service'),
    ('/resources/{pk}/delete/ingress', 'ingress'),
    ('/resources/{pk}/delete/configmap', 'configmap'),
    ('/resources/{pk}/delete/secret', 'secret'),
    ('/resources/{pk}/delete/persistentvolumeclaim', 'pvc'),
    # 集群和节点
    ('/clusters/{pk}/nodes/', 'node'),
    ('/clusters/{pk}/node/', 'node'),
]

# 写操作关键词
WRITE_KEYWORDS = ('scale', 'restart', 'create', 'delete', 'cordon', 'uncordon', 'drain')


class LoginRequiredMiddleware(MiddlewareMixin):
    """全局登录拦截"""

    def process_request(self, request):
        if request.user.is_authenticated:
            return None

        path = request.path
        for exempt in LOGIN_EXEMPT_URLS:
            if path.startswith(exempt):
                return None

        if _is_ajax(request):
            return JsonResponse({'error': '未登录'}, status=401)

        return redirect(f'/accounts/login/?next={path}')


class PermissionMiddleware(MiddlewareMixin):
    """模块级权限拦截"""

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # 管理员跳过
        if _is_admin(request.user):
            return None

        path = request.path

        # 只拦截 /resources/ 和 /clusters/<pk>/nodes|node|metrics 路径
        if not path.startswith('/resources/') and not self._is_cluster_module_path(path):
            # 拦截用户管理和权限管理（只有管理员能访问）
            if path.startswith('/accounts/users/') or path.startswith('/accounts/permissions/'):
                return _deny(request, '仅管理员可访问')
            return None

        # 提取集群 ID
        cluster_id = self._extract_cluster_id(path)
        if not cluster_id:
            return None

        # 识别模块
        module = self._resolve_module(path, cluster_id)
        if not module:
            return None

        # 查询用户对该集群该模块的权限
        perm = UserModulePermission.objects.filter(
            user=request.user,
            cluster_id=cluster_id,
            module=module,
        ).first()

        if not perm:
            return _deny(request, f'无权访问「{self._module_label(module)}」模块')

        # 判断操作类型
        is_write = self._is_write_action(request, path)

        if is_write and not perm.can_edit():
            return _deny(request, f'无权编辑「{self._module_label(module)}」模块，当前仅有查看权限')

        # 注入权限信息供模板使用
        request.user_can_edit = perm.can_edit()
        request.user_can_delete = perm.can_edit()  # 编辑权限包含删除
        request.current_module = module

        return None

    def _is_cluster_module_path(self, path):
        """判断是否是集群模块路径（节点管理、metrics）"""
        if not path.startswith('/clusters/'):
            return False
        parts = path.strip('/').split('/')
        if len(parts) >= 3:
            return parts[2] in ('nodes', 'node', 'metrics')
        return False

    def _extract_cluster_id(self, path):
        """从路径中提取集群 ID"""
        parts = path.strip('/').split('/')
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return None

    def _resolve_module(self, path, cluster_id):
        """根据路径解析对应的模块"""
        for pattern, module in MODULE_MAPPING:
            resolved = pattern.replace('{pk}', str(cluster_id))
            if path.startswith(resolved):
                return module
        return None

    def _is_write_action(self, request, path):
        """判断是否是写操作"""
        if request.method == 'POST':
            return True
        return False

    def _module_label(self, module):
        """获取模块中文名"""
        for code, label in UserModulePermission.MODULE_CHOICES:
            if code == module:
                return label
        return module


def _is_admin(user):
    profile = getattr(user, 'profile', None)
    if profile:
        return profile.is_admin()
    return user.is_superuser


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.content_type == 'application/json' or \
           request.method == 'POST'


def _deny(request, message):
    if _is_ajax(request):
        return JsonResponse({'error': message}, status=403)
    from django.shortcuts import render
    return render(request, 'accounts/forbidden.html', {'error_message': message}, status=403)
