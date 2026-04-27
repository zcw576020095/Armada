"""K8s 资源操作管理类"""
import logging
import yaml
from kubernetes import client
from kubernetes.client.rest import ApiException

from clusters.k8s_client import k8s_pool

logger = logging.getLogger(__name__)


class K8sResourceManager:
    """K8s 资源操作基类"""

    # 资源类型映射配置
    RESOURCE_TYPES = {
        'namespace': {
            'api': 'core_v1',
            'list': 'list_namespace',
            'get': 'read_namespace',
            'create': 'create_namespace',
            'delete': 'delete_namespace',
            'patch': 'patch_namespace',
            'replace': 'replace_namespace',
            'namespaced': False,
        },
        'deployment': {
            'api': 'apps_v1',
            'list': 'list_namespaced_deployment',
            'list_all': 'list_deployment_for_all_namespaces',
            'get': 'read_namespaced_deployment',
            'create': 'create_namespaced_deployment',
            'delete': 'delete_namespaced_deployment',
            'patch': 'patch_namespaced_deployment',
            'replace': 'replace_namespaced_deployment',
            'namespaced': True,
        },
        'statefulset': {
            'api': 'apps_v1',
            'list': 'list_namespaced_stateful_set',
            'list_all': 'list_stateful_set_for_all_namespaces',
            'get': 'read_namespaced_stateful_set',
            'create': 'create_namespaced_stateful_set',
            'delete': 'delete_namespaced_stateful_set',
            'patch': 'patch_namespaced_stateful_set',
            'replace': 'replace_namespaced_stateful_set',
            'namespaced': True,
        },
        'daemonset': {
            'api': 'apps_v1',
            'list': 'list_namespaced_daemon_set',
            'list_all': 'list_daemon_set_for_all_namespaces',
            'get': 'read_namespaced_daemon_set',
            'create': 'create_namespaced_daemon_set',
            'delete': 'delete_namespaced_daemon_set',
            'patch': 'patch_namespaced_daemon_set',
            'replace': 'replace_namespaced_daemon_set',
            'namespaced': True,
        },
        'pod': {
            'api': 'core_v1',
            'list': 'list_namespaced_pod',
            'list_all': 'list_pod_for_all_namespaces',
            'get': 'read_namespaced_pod',
            'delete': 'delete_namespaced_pod',
            'patch': 'patch_namespaced_pod',
            'replace': 'replace_namespaced_pod',
            'namespaced': True,
        },
        'service': {
            'api': 'core_v1',
            'list': 'list_namespaced_service',
            'list_all': 'list_service_for_all_namespaces',
            'get': 'read_namespaced_service',
            'create': 'create_namespaced_service',
            'delete': 'delete_namespaced_service',
            'patch': 'patch_namespaced_service',
            'replace': 'replace_namespaced_service',
            'namespaced': True,
        },
        'ingress': {
            'api': 'networking_v1',
            'list': 'list_namespaced_ingress',
            'list_all': 'list_ingress_for_all_namespaces',
            'get': 'read_namespaced_ingress',
            'create': 'create_namespaced_ingress',
            'delete': 'delete_namespaced_ingress',
            'patch': 'patch_namespaced_ingress',
            'replace': 'replace_namespaced_ingress',
            'namespaced': True,
        },
        'configmap': {
            'api': 'core_v1',
            'list': 'list_namespaced_config_map',
            'list_all': 'list_config_map_for_all_namespaces',
            'get': 'read_namespaced_config_map',
            'create': 'create_namespaced_config_map',
            'delete': 'delete_namespaced_config_map',
            'patch': 'patch_namespaced_config_map',
            'replace': 'replace_namespaced_config_map',
            'namespaced': True,
        },
        'secret': {
            'api': 'core_v1',
            'list': 'list_namespaced_secret',
            'list_all': 'list_secret_for_all_namespaces',
            'get': 'read_namespaced_secret',
            'create': 'create_namespaced_secret',
            'delete': 'delete_namespaced_secret',
            'patch': 'patch_namespaced_secret',
            'replace': 'replace_namespaced_secret',
            'namespaced': True,
        },
        'persistentvolumeclaim': {
            'api': 'core_v1',
            'list': 'list_namespaced_persistent_volume_claim',
            'list_all': 'list_persistent_volume_claim_for_all_namespaces',
            'get': 'read_namespaced_persistent_volume_claim',
            'create': 'create_namespaced_persistent_volume_claim',
            'delete': 'delete_namespaced_persistent_volume_claim',
            'patch': 'patch_namespaced_persistent_volume_claim',
            'replace': 'replace_namespaced_persistent_volume_claim',
            'namespaced': True,
        },
    }

    def __init__(self, cluster):
        self.cluster = cluster
        self.core_v1 = k8s_pool.core_v1(cluster)
        self.apps_v1 = k8s_pool.apps_v1(cluster)
        self.networking_v1 = k8s_pool.networking_v1(cluster)

    def _get_api_client(self, api_name):
        """获取对应的 API 客户端"""
        return getattr(self, api_name)

    def get_resource(self, resource_type, name, namespace=None):
        """获取单个资源"""
        config = self.RESOURCE_TYPES.get(resource_type)
        if not config:
            raise ValueError(f"Unknown resource type: {resource_type}")

        api_client = self._get_api_client(config['api'])
        get_method = getattr(api_client, config['get'])

        try:
            if config['namespaced']:
                return get_method(name, namespace, _request_timeout=5)
            else:
                return get_method(name, _request_timeout=5)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"{resource_type.capitalize()} '{name}' not found")
            raise Exception(f"Failed to get {resource_type}: {e.reason}")

    def get_resource_yaml(self, resource_type, name, namespace=None):
        """获取资源的 YAML 表示"""
        resource = self.get_resource(resource_type, name, namespace)
        # 移除 managed fields 等冗余信息
        if hasattr(resource, 'metadata') and hasattr(resource.metadata, 'managed_fields'):
            resource.metadata.managed_fields = None
        return yaml.dump(client.ApiClient().sanitize_for_serialization(resource), default_flow_style=False)

    def delete_resource(self, resource_type, name, namespace=None, force=False):
        """删除资源。

        force=True 时对 Pod 启用强制删除：跳过 30 秒优雅退出期立即清除。
        ⚠️ 对 StatefulSet / 带 PV / 有状态服务不安全，可能导致 PV 挂载冲突或数据丢失，
        因此仅作用于 Pod 类型，其他资源传 force=True 也会被忽略。
        """
        config = self.RESOURCE_TYPES.get(resource_type)
        if not config:
            raise ValueError(f"Unknown resource type: {resource_type}")

        api_client = self._get_api_client(config['api'])
        delete_method = getattr(api_client, config['delete'])

        kwargs = {'_request_timeout': 10}
        if force and resource_type == 'pod':
            kwargs['grace_period_seconds'] = 0
            kwargs['propagation_policy'] = 'Background'

        try:
            if config['namespaced']:
                delete_method(name, namespace, **kwargs)
            else:
                delete_method(name, **kwargs)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"{resource_type.capitalize()} '{name}' not found")
            raise Exception(f"Failed to delete {resource_type}: {e.reason}")

    @staticmethod
    def _strip_server_managed_fields(doc):
        """移除 K8s 服务端维护的只读字段。

        - 创建对象时这些字段不能出现（否则 K8s 拒绝："resourceVersion should not be set on objects to be created"）
        - 更新对象时 resourceVersion 会被重新注入（用于乐观锁），其他字段保持移除
        - status 整块由 K8s 管理，apply 时不应包含
        """
        metadata = doc.get('metadata') or {}
        for key in (
            'resourceVersion', 'uid', 'creationTimestamp', 'generation',
            'managedFields', 'selfLink', 'deletionTimestamp',
            'deletionGracePeriodSeconds', 'ownerReferences',
        ):
            metadata.pop(key, None)
        if 'metadata' in doc and not metadata:
            doc['metadata'] = {}
        doc.pop('status', None)

    def apply_yaml(self, yaml_content):
        """应用 YAML 配置（整体替换，不存在则创建）。

        使用 replace 而非 patch —— patch 是 strategic merge，删除的字段不会生效，
        而 replace 会整体替换资源，符合"应用"的语义。

        注意：先 strip 掉 K8s 服务端字段，否则改 name 后走创建流程会被 K8s 拒绝；
        replace 时再单独注入 resourceVersion 作为乐观锁。

        返回值结构：
        {
          'success': bool,
          'message': str,
          'actions': [{'kind', 'name', 'namespace', 'action': 'created'|'updated', 'resource'?: {...}}]
        }
        前端可据此触发列表的乐观更新，避免整页 reload。
        """
        try:
            docs = list(yaml.safe_load_all(yaml_content))
            results = []
            actions = []

            for doc in docs:
                if not doc or not isinstance(doc, dict):
                    continue

                kind = doc.get('kind', '').lower()
                name = doc.get('metadata', {}).get('name')
                namespace = doc.get('metadata', {}).get('namespace', 'default')

                if not kind or not name:
                    raise Exception("Invalid YAML: missing 'kind' or 'metadata.name'")

                config = self.RESOURCE_TYPES.get(kind)
                if not config:
                    raise Exception(f"Unsupported resource type: {kind}")

                self._strip_server_managed_fields(doc)

                api_client = self._get_api_client(config['api'])

                try:
                    get_method = getattr(api_client, config['get'])
                    if config['namespaced']:
                        existing = get_method(name, namespace, _request_timeout=5)
                    else:
                        existing = get_method(name, _request_timeout=5)

                    doc.setdefault('metadata', {})
                    doc['metadata']['resourceVersion'] = existing.metadata.resource_version

                    replace_name = config.get('replace')
                    if not replace_name:
                        raise Exception(f"Resource type {kind} does not support replace")
                    replace_method = getattr(api_client, replace_name)
                    if config['namespaced']:
                        replace_method(name, namespace, doc, _request_timeout=10)
                    else:
                        replace_method(name, doc, _request_timeout=10)
                    results.append(f"Updated {kind} '{name}'")
                    actions.append({
                        'kind': kind,
                        'name': name,
                        'namespace': namespace if config['namespaced'] else '',
                        'action': 'updated',
                    })

                except ApiException as e:
                    if e.status == 404 and config.get('create'):
                        create_method = getattr(api_client, config['create'])
                        if config['namespaced']:
                            created = create_method(namespace, doc, _request_timeout=10)
                        else:
                            created = create_method(doc, _request_timeout=10)
                        results.append(f"Created {kind} '{name}'")

                        action_entry = {
                            'kind': kind,
                            'name': name,
                            'namespace': namespace if config['namespaced'] else '',
                            'action': 'created',
                        }
                        # 复用 sync_service 的统一序列化函数生成 resource 数据，
                        # 让前端 markAdded 插入的乐观项与正常列表数据格式完全一致
                        try:
                            from resources.sync_service import _serialize_item
                            action_entry['resource'] = _serialize_item(kind, created)
                        except Exception as serr:
                            logger.warning(f'Failed to serialize new {kind} {name}: {serr}')
                            action_entry['resource'] = {
                                'name': name,
                                'namespace': namespace if config['namespaced'] else '',
                                'age': '0s',
                            }
                        actions.append(action_entry)
                    else:
                        detail = e.body or e.reason or str(e)
                        raise Exception(f"{e.reason}: {detail[:500]}")

            return {'success': True, 'message': '; '.join(results), 'actions': actions}
        except yaml.YAMLError as e:
            return {'success': False, 'error': f'Invalid YAML: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # Deployment 特定操作
    def scale_deployment(self, name, namespace, replicas):
        """扩缩容 Deployment"""
        try:
            body = {'spec': {'replicas': replicas}}
            self.apps_v1.patch_namespaced_deployment_scale(
                name, namespace, body, _request_timeout=10
            )
        except ApiException as e:
            raise Exception(f"Failed to scale deployment: {e.reason}")

    def restart_deployment(self, name, namespace):
        """重启 Deployment（通过添加 annotation 触发滚动更新）"""
        try:
            from datetime import datetime
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': datetime.utcnow().isoformat()
                            }
                        }
                    }
                }
            }
            self.apps_v1.patch_namespaced_deployment(
                name, namespace, body, _request_timeout=10
            )
        except ApiException as e:
            raise Exception(f"Failed to restart deployment: {e.reason}")

    # StatefulSet 特定操作
    def scale_statefulset(self, name, namespace, replicas):
        """扩缩容 StatefulSet"""
        try:
            body = {'spec': {'replicas': replicas}}
            self.apps_v1.patch_namespaced_stateful_set_scale(
                name, namespace, body, _request_timeout=10
            )
        except ApiException as e:
            raise Exception(f"Failed to scale statefulset: {e.reason}")

    def restart_statefulset(self, name, namespace):
        """重启 StatefulSet"""
        try:
            from datetime import datetime
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': datetime.utcnow().isoformat()
                            }
                        }
                    }
                }
            }
            self.apps_v1.patch_namespaced_stateful_set(
                name, namespace, body, _request_timeout=10
            )
        except ApiException as e:
            raise Exception(f"Failed to restart statefulset: {e.reason}")
