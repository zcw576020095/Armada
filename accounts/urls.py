from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),

    # 用户管理
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/update/', views.user_update, name='user_update'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),

    # 权限管理
    path('permissions/', views.permission_list, name='permission_list'),
    path('permissions/create/', views.permission_create, name='permission_create'),
    path('permissions/<int:perm_id>/delete/', views.permission_delete, name='permission_delete'),
]
