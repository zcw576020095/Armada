from django.urls import path
from . import views

app_name = 'clusters'

urlpatterns = [
    path('', views.cluster_list, name='list'),
    path('add/', views.cluster_add, name='add'),
    path('<int:pk>/', views.cluster_detail, name='detail'),
    path('<int:pk>/edit/', views.cluster_edit, name='edit'),
    path('<int:pk>/delete/', views.cluster_delete, name='delete'),
    path('<int:pk>/refresh/', views.cluster_refresh, name='refresh'),
    path('<int:pk>/prometheus/', views.cluster_update_prometheus, name='update_prometheus'),
    path('<int:pk>/debug-prom/', views.cluster_debug_prom, name='debug_prom'),
    path('<int:pk>/select/', views.cluster_select, name='select'),
    path('<int:pk>/nodes/', views.cluster_nodes_api, name='nodes_api'),
    path('<int:pk>/nodes/manage/', views.cluster_nodes, name='nodes'),
    path('<int:pk>/metrics/', views.cluster_metrics_api, name='metrics_api'),
    path('<int:pk>/node/<str:node_name>/', views.node_detail, name='node_detail'),
    path('<int:pk>/node/<str:node_name>/info/', views.node_info_api, name='node_info_api'),
    path('<int:pk>/node/<str:node_name>/cordon/', views.node_cordon, name='node_cordon'),
    path('<int:pk>/node/<str:node_name>/uncordon/', views.node_uncordon, name='node_uncordon'),
    path('<int:pk>/node/<str:node_name>/drain/', views.node_drain, name='node_drain'),
    path('<int:pk>/node/<str:node_name>/delete/', views.node_delete, name='node_delete'),
    path('<int:pk>/pod/<str:namespace>/<str:pod_name>/logs/', views.pod_logs_api, name='pod_logs'),
]
