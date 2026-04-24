"""K8s 资源操作管理类"""
import yaml
from kubernetes import client
from kubernetes.client.rest import ApiException

from clusters.k8s_client import k8s_pool


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
            'namespaced': True,
        },
        'pod': {
            'api': 'core_v1',
            'list': 'list_namespaced_pod',
            'list_all': 'list_pod_for_all_namespaces',
            'get': 'read_namespaced_pod',
            'delete': 'delete_namespaced_pod',
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

    def list_resources(self, resource_type, namespace=None, label_selector=None, field_selector=None):
        """列出资源"""
        config = self.RESOURCE_TYPES.get(resource_type)
        if not config:
            raise ValueError(f"Unknown resource type: {resource_type}")

        api_client = self._get_api_client(config['api'])
        list_method = getattr(api_client, config['list'])

        kwargs = {'_request_timeout': 10}
        if label_selector:
            kwargs['label_selector'] = label_selector
        if field_selector:
            kwargs['field_selector'] = field_selector

        try:
            if config['namespaced']:
                if namespace:
                    result = list_method(namespace, **kwargs)
                else:
                    # Use list_*_for_all_namespaces for cross-namespace listing
                    list_all_name = config.get('list_all')
                    if list_all_name:
                        list_all_method = getattr(api_client, list_all_name)
                        result = list_all_method(**kwargs)
                    else:
                        result = list_method(namespace='', **kwargs)
            else:
                result = list_method(**kwargs)
            return result.items
        except ApiException as e:
            raise Exception(f"Failed to list {resource_type}: {e.reason}")

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

    def delete_resource(self, resource_type, name, namespace=None):
        """删除资源"""
        config = self.RESOURCE_TYPES.get(resource_type)
        if not config:
            raise ValueError(f"Unknown resource type: {resource_type}")

        api_client = self._get_api_client(config['api'])
        delete_method = getattr(api_client, config['delete'])

        try:
            if config['namespaced']:
                delete_method(name, namespace, _request_timeout=10)
            else:
                delete_method(name, _request_timeout=10)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"{resource_type.capitalize()} '{name}' not found")
            raise Exception(f"Failed to delete {resource_type}: {e.reason}")

    def apply_yaml(self, yaml_content):
        """应用 YAML 配置（创建或更新资源）"""
        try:
            docs = list(yaml.safe_load_all(yaml_content))
            results = []

            for doc in docs:
                if not doc or not isinstance(doc, dict):
                    continue

                kind = doc.get('kind', '').lower()
                name = doc.get('metadata', {}).get('name')
                namespace = doc.get('metadata', {}).get('namespace', 'default')

                if not kind or not name:
                    raise Exception("Invalid YAML: missing 'kind' or 'metadata.name'")

                # 映射 kind 到 resource_type
                resource_type = kind
                if kind == 'persistentvolumeclaim':
                    resource_type = 'persistentvolumeclaim'

                config = self.RESOURCE_TYPES.get(resource_type)
                if not config:
                    raise Exception(f"Unsupported resource type: {kind}")

                api_client = self._get_api_client(config['api'])

                # 尝试更新，如果不存在则创建
                try:
                    if config.get('patch'):
                        patch_method = getattr(api_client, config['patch'])
                        if config['namespaced']:
                            patch_method(name, namespace, doc, _request_timeout=10)
                        else:
                            patch_method(name, doc, _request_timeout=10)
                        results.append(f"Updated {kind} '{name}'")
                except ApiException as e:
                    if e.status == 404 and config.get('create'):
                        # 资源不存在，创建
                        create_method = getattr(api_client, config['create'])
                        if config['namespaced']:
                            create_method(namespace, doc, _request_timeout=10)
                        else:
                            create_method(doc, _request_timeout=10)
                        results.append(f"Created {kind} '{name}'")
                    else:
                        raise

            return {'success': True, 'message': '; '.join(results)}
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

    def rollback_deployment(self, name, namespace, revision=None):
        """回滚 Deployment 到指定版本"""
        try:
            # 获取 ReplicaSet 历史
            rs_list = self.apps_v1.list_namespaced_replica_set(
                namespace,
                label_selector=f'app={name}',
                _request_timeout=5
            )

            if not rs_list.items:
                raise Exception("No revision history found")

            # 按 revision 排序
            rs_list.items.sort(
                key=lambda x: int(x.metadata.annotations.get('deployment.kubernetes.io/revision', '0')),
                reverse=True
            )

            if revision:
                target_rs = next(
                    (rs for rs in rs_list.items
                     if rs.metadata.annotations.get('deployment.kubernetes.io/revision') == str(revision)),
                    None
                )
            else:
                # 回滚到上一个版本
                target_rs = rs_list.items[1] if len(rs_list.items) > 1 else None

            if not target_rs:
                raise Exception(f"Revision {revision} not found")

            # 更新 Deployment 的 template
            body = {'spec': {'template': target_rs.spec.template}}
            self.apps_v1.patch_namespaced_deployment(
                name, namespace, body, _request_timeout=10
            )
        except ApiException as e:
            raise Exception(f"Failed to rollback deployment: {e.reason}")

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

    # Pod 特定操作
    def get_pod_logs(self, name, namespace, container=None, tail_lines=100):
        """获取 Pod 日志"""
        try:
            kwargs = {
                'name': name,
                'namespace': namespace,
                'tail_lines': tail_lines,
                '_request_timeout': 10,
            }
            if container:
                kwargs['container'] = container
            return self.core_v1.read_namespaced_pod_log(**kwargs)
        except ApiException as e:
            raise Exception(f"Failed to get pod logs: {e.reason}")
