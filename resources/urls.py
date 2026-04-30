from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    # Namespaces
    path('<int:pk>/namespaces/', views.namespace_list, name='namespaces'),
    path('<int:pk>/namespaces/create/', views.namespace_create, name='namespace_create'),
    path('<int:pk>/namespaces/<str:name>/delete/', views.namespace_delete, name='namespace_delete'),
    path('<int:pk>/namespaces/<str:name>/force-finalize/', views.namespace_force_finalize, name='namespace_force_finalize'),

    # Deployments
    path('<int:pk>/deployments/', views.deployment_list, name='deployments'),
    path('<int:pk>/deployments/<str:ns>/<str:name>/scale/', views.deployment_scale, name='deployment_scale'),
    path('<int:pk>/deployments/<str:ns>/<str:name>/restart/', views.deployment_restart, name='deployment_restart'),
    path('<int:pk>/api/deployments/<str:ns>/<str:name>/describe/', views.deployment_describe_api, name='deployment_describe'),
    path('<int:pk>/api/deployments/<str:ns>/<str:name>/revisions/', views.deployment_revisions_api, name='deployment_revisions'),
    path('<int:pk>/deployments/<str:ns>/<str:name>/rollback/', views.deployment_rollback, name='deployment_rollback'),

    # StatefulSets
    path('<int:pk>/statefulsets/', views.statefulset_list, name='statefulsets'),
    path('<int:pk>/statefulsets/<str:ns>/<str:name>/scale/', views.statefulset_scale, name='statefulset_scale'),
    path('<int:pk>/statefulsets/<str:ns>/<str:name>/restart/', views.statefulset_restart, name='statefulset_restart'),

    # DaemonSets
    path('<int:pk>/daemonsets/', views.daemonset_list, name='daemonsets'),

    # Pods
    path('<int:pk>/pods/', views.pod_list, name='pods'),
    path('<int:pk>/pods/<str:namespace>/<str:pod_name>/logs/', views.pod_logs, name='pod_logs'),

    # Services
    path('<int:pk>/services/', views.service_list, name='services'),

    # Ingresses
    path('<int:pk>/ingresses/', views.ingress_list, name='ingresses'),

    # ConfigMaps
    path('<int:pk>/configmaps/', views.configmap_list, name='configmaps'),

    # Secrets
    path('<int:pk>/secrets/', views.secret_list, name='secrets'),

    # PVCs
    path('<int:pk>/pvcs/', views.pvc_list, name='pvcs'),

    # ─── API endpoints (JSON, for async loading) ─────────────
    path('<int:pk>/api/namespaces/', views.namespace_list_api, name='namespaces_api'),
    path('<int:pk>/api/deployments/', views.deployment_list_api, name='deployments_api'),
    path('<int:pk>/api/statefulsets/', views.statefulset_list_api, name='statefulsets_api'),
    path('<int:pk>/api/daemonsets/', views.daemonset_list_api, name='daemonsets_api'),
    path('<int:pk>/api/pods/', views.pod_list_api, name='pods_api'),
    path('<int:pk>/api/services/', views.service_list_api, name='services_api'),
    path('<int:pk>/api/ingresses/', views.ingress_list_api, name='ingresses_api'),
    path('<int:pk>/api/configmaps/', views.configmap_list_api, name='configmaps_api'),
    path('<int:pk>/api/secrets/', views.secret_list_api, name='secrets_api'),
    path('<int:pk>/api/pvcs/', views.pvc_list_api, name='pvcs_api'),

    # ─── Generic Apply (通用 YAML 创建/更新) ─────────────────
    path('<int:pk>/apply/', views.resource_apply_api, name='resource_apply'),
    path('<int:pk>/validate/', views.resource_validate_api, name='resource_validate'),

    # ─── Generic YAML & Delete ───────────────────────────────
    path('<int:pk>/yaml/<str:resource_type>/<str:ns>/<str:name>/', views.resource_yaml_api, name='resource_yaml'),
    path('<int:pk>/yaml/<str:resource_type>/<str:name>/', views.resource_yaml_api, name='resource_yaml_cluster'),
    path('<int:pk>/delete/<str:resource_type>/<str:ns>/<str:name>/', views.resource_delete_api, name='resource_delete'),
    path('<int:pk>/delete/<str:resource_type>/<str:name>/', views.resource_delete_api, name='resource_delete_cluster'),
]
