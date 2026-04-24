from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import UserModulePermission, is_admin_user


# 不需要登录的路径
LOGIN_EXEMPT_URLS = [
    '/accounts/login/',
    '/admin/',
    '/static/',
]

# URL 路径 -> 模块映射
# 格式: (路径前缀, 模块名)
# 注意：顺序敏感 —— 匹配时按顺序 startswith，更具体的路径必须放在更宽泛的路径前面
MODULE_MAPPING = [
    # resources 模块（资源列表页）
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
    # yaml/delete 通用 API（更长的路径放前面防止误匹配，如 persistentvolumeclaim 前缀比 pod 长）
    ('/resources/{pk}/yaml/persistentvolumeclaim', 'pvc'),
    ('/resources/{pk}/yaml/namespace', 'namespace'),
    ('/resources/{pk}/yaml/deployment', 'deployment'),
    ('/resources/{pk}/yaml/statefulset', 'statefulset'),
    ('/resources/{pk}/yaml/daemonset', 'daemonset'),
    ('/resources/{pk}/yaml/pod', 'pod'),
    ('/resources/{pk}/yaml/service', 'service'),
    ('/resources/{pk}/yaml/ingress', 'ingress'),
    ('/resources/{pk}/yaml/configmap', 'configmap'),
    ('/resources/{pk}/yaml/secret', 'secret'),
    ('/resources/{pk}/delete/persistentvolumeclaim', 'pvc'),
    ('/resources/{pk}/delete/namespace', 'namespace'),
    ('/resources/{pk}/delete/deployment', 'deployment'),
    ('/resources/{pk}/delete/statefulset', 'statefulset'),
    ('/resources/{pk}/delete/daemonset', 'daemonset'),
    ('/resources/{pk}/delete/pod', 'pod'),
    ('/resources/{pk}/delete/service', 'service'),
    ('/resources/{pk}/delete/ingress', 'ingress'),
    ('/resources/{pk}/delete/configmap', 'configmap'),
    ('/resources/{pk}/delete/secret', 'secret'),
    # 集群下的节点管理
    ('/clusters/{pk}/nodes/', 'node'),
    ('/clusters/{pk}/node/', 'node'),
    # 集群下的 Pod 日志 API（归属 pod 模块）
    ('/clusters/{pk}/pod/', 'pod'),
    # 集群管理本身 —— 必须放在最后，作为 /clusters/{pk}/ 下所有未命中的路径的 fallback
    # 匹配：/clusters/{pk}/ 详情、/edit、/delete、/refresh、/prometheus、/debug-prom、/metrics
    ('/clusters/{pk}/', 'cluster'),
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

    # 管理员专属路径（普通用户拒绝）
    ADMIN_ONLY_PATHS = (
        '/accounts/users/',
        '/accounts/permissions/',
        '/clusters/add/',
    )

    # 登录即可、不做权限校验的路径
    PUBLIC_AUTH_PATHS = (
        '/accounts/profile/',
        '/accounts/logout/',
    )

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        # 管理员跳过所有权限校验
        if is_admin_user(request.user):
            return None

        path = request.path

        # 1. 登录即可访问的路径（个人设置、登出）
        if any(path.startswith(p) for p in self.PUBLIC_AUTH_PATHS):
            return None

        # 2. 管理员专属：用户管理、权限管理、添加集群
        if any(path.startswith(p) for p in self.ADMIN_ONLY_PATHS):
            return _deny(request, '该功能仅管理员可访问')

        # 3. Dashboard（根路径 /）—— 需要对任一集群有 dashboard 模块权限
        if path == '/':
            has_dashboard = UserModulePermission.objects.filter(
                user=request.user, module='dashboard',
            ).exists()
            if not has_dashboard:
                return _deny(request, '无权访问「仪表盘」模块')
            return None

        # 4. 集群列表页 /clusters/ —— 放行（view 自行过滤展示范围）
        if path == '/clusters/':
            return None

        # 5. 集群切换 /clusters/<pk>/select/ —— 放行（仅改 session，不泄露数据）
        if path.startswith('/clusters/') and path.endswith('/select/'):
            return None

        # 6. 非 /resources/ 与 /clusters/ 的路径（兜底放行）
        if not path.startswith('/resources/') and not path.startswith('/clusters/'):
            return None

        # 7. 进入按 cluster_id + module 细粒度权限校验
        cluster_id = self._extract_cluster_id(path)
        if not cluster_id:
            return None

        module = self._resolve_module(path, cluster_id)
        if not module:
            return None

        perm = UserModulePermission.objects.filter(
            user=request.user,
            cluster_id=cluster_id,
            module=module,
        ).first()

        if not perm:
            return _deny(request, f'无权访问「{self._module_label(module)}」模块')

        # 写操作需要 edit 权限
        if self._is_write_action(request, path) and not perm.can_edit():
            return _deny(request, f'无权编辑「{self._module_label(module)}」模块，当前仅有查看权限')

        # 注入权限信息供模板使用
        request.user_can_edit = perm.can_edit()
        request.user_can_delete = perm.can_edit()
        request.current_module = module

        return None

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


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' \
        or request.content_type == 'application/json' \
        or request.headers.get('Accept', '').startswith('application/json')


def _deny(request, message):
    if _is_ajax(request):
        return JsonResponse({'error': message}, status=403)
    from django.shortcuts import render
    return render(request, 'accounts/forbidden.html', {'error_message': message}, status=403)
