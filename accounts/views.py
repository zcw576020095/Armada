import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from clusters.models import Cluster
from .models import UserProfile, UserModulePermission, is_admin_user


# ─── 登录/登出 ─────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    # 处理从 CSRF 失败页等跳回时附带的提示
    error = ''
    username = ''
    msg_code = request.GET.get('msg', '')
    if msg_code == 'session_expired':
        error = '会话已过期，请重新登录'

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)

        # 密码正确但账户被禁用 → 明确提示；其他情况一律模糊提示（防止用户名探测）
        try:
            candidate = User.objects.get(username=username)
            if not candidate.is_active and candidate.check_password(password):
                error = '该账户已被禁用，请联系管理员'
            else:
                error = '用户名或密码错误'
        except User.DoesNotExist:
            error = '用户名或密码错误'

    return render(request, 'accounts/login.html', {'error': error, 'username': username})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')


def csrf_failure_view(request, reason=''):
    """CSRF 校验失败时的友好处理：清理 session 并跳回登录页并提示"""
    logout(request)
    return redirect('/accounts/login/?msg=session_expired')


# ─── 用户管理 ──────────────────────────────────────────────

@login_required
def user_list(request):
    if not is_admin_user(request.user):
        return render(request, 'accounts/forbidden.html', status=403)

    users = User.objects.select_related('profile').order_by('-date_joined')
    return render(request, 'accounts/user_list.html', {'users': users})


@login_required
@require_POST
def user_create(request):
    if not is_admin_user(request.user):
        return JsonResponse({'error': '无权限'}, status=403)

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    role = request.POST.get('role', 'user')
    department = request.POST.get('department', '')

    if not username or not password:
        return JsonResponse({'error': '用户名和密码不能为空'}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': '用户名已存在'}, status=400)

    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, role=role, department=department)
    return JsonResponse({'success': True})


@login_required
@require_POST
def user_update(request, user_id):
    if not is_admin_user(request.user):
        return JsonResponse({'error': '无权限'}, status=403)

    target = get_object_or_404(User, pk=user_id)
    data = json.loads(request.body)

    if 'role' in data:
        profile, _ = UserProfile.objects.get_or_create(user=target)
        profile.role = data['role']
        profile.department = data.get('department', profile.department)
        profile.save()

    if data.get('password'):
        target.set_password(data['password'])
        target.save()

    if 'is_active' in data:
        target.is_active = data['is_active']
        target.save()

    return JsonResponse({'success': True})


@login_required
@require_POST
def user_delete(request, user_id):
    if not is_admin_user(request.user):
        return JsonResponse({'error': '无权限'}, status=403)

    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        return JsonResponse({'error': '不能删除自己'}, status=400)
    target.delete()
    return JsonResponse({'success': True})


# ─── 权限管理 ──────────────────────────────────────────────

@login_required
def permission_list(request):
    if not is_admin_user(request.user):
        return render(request, 'accounts/forbidden.html', status=403)

    permissions = UserModulePermission.objects.select_related('user', 'cluster').all()
    users = User.objects.filter(profile__role='user')
    clusters = Cluster.objects.all()
    return render(request, 'accounts/permission_list.html', {
        'permissions': permissions,
        'users': users,
        'clusters': clusters,
        'module_choices': UserModulePermission.MODULE_CHOICES,
        'permission_choices': UserModulePermission.PERMISSION_CHOICES,
    })


@login_required
@require_POST
def permission_create(request):
    if not is_admin_user(request.user):
        return JsonResponse({'error': '无权限'}, status=403)

    user_id = request.POST.get('user_id')
    cluster_id = request.POST.get('cluster_id')
    modules = request.POST.getlist('modules')  # 多选模块
    permission = request.POST.get('permission', 'view')

    if not modules:
        return JsonResponse({'error': '请至少选择一个模块'}, status=400)

    user = get_object_or_404(User, pk=user_id)
    cluster = get_object_or_404(Cluster, pk=cluster_id)

    created_count = 0
    for module in modules:
        _, created = UserModulePermission.objects.update_or_create(
            user=user, cluster=cluster, module=module,
            defaults={'permission': permission}
        )
        if created:
            created_count += 1

    return JsonResponse({'success': True, 'created': created_count, 'updated': len(modules) - created_count})


@login_required
@require_POST
def permission_delete(request, perm_id):
    if not is_admin_user(request.user):
        return JsonResponse({'error': '无权限'}, status=403)

    perm = get_object_or_404(UserModulePermission, pk=perm_id)
    perm.delete()
    return JsonResponse({'success': True})


# ─── 个人设置 ──────────────────────────────────────────────

@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        department = request.POST.get('department', '').strip()
        new_password = request.POST.get('new_password', '')

        profile.phone = phone
        profile.department = department
        profile.save()

        if new_password:
            request.user.set_password(new_password)
            request.user.save()
            login(request, request.user)

        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'profile': profile})


