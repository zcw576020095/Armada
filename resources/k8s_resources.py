"""K8s 资源操作管理类"""
import copy
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
        """获取资源的 YAML 表示。

        参考 kubectl edit 的处理：剥掉 K8s 运行时维护的字段（status、metadata 里的
        resourceVersion / uid / managedFields 等），用户编辑界面里只看到"配置部分"，
        避免出现"GET 时带着 status，用户没动它，apply 时却被静默忽略"这种迷惑场景。
        """
        resource = self.get_resource(resource_type, name, namespace)
        if hasattr(resource, 'metadata') and hasattr(resource.metadata, 'managed_fields'):
            resource.metadata.managed_fields = None
        doc = client.ApiClient().sanitize_for_serialization(resource)
        if isinstance(doc, dict):
            doc.pop('status', None)
            metadata = doc.get('metadata') or {}
            for key in (
                'resourceVersion', 'uid', 'creationTimestamp', 'generation',
                'managedFields', 'selfLink', 'deletionTimestamp',
                'deletionGracePeriodSeconds', 'ownerReferences',
            ):
                metadata.pop(key, None)
            # 清掉 kubectl.kubernetes.io/last-applied-configuration 这种巨型注解，
            # 用户编辑时根本不该看到（kubectl edit 也会自动隐藏它）
            anns = metadata.get('annotations') or {}
            anns.pop('kubectl.kubernetes.io/last-applied-configuration', None)
            if not anns and 'annotations' in metadata:
                metadata.pop('annotations', None)
            # 剥掉 selector / spec.template 上的 pod-template-hash —— 这是 controller
            # 自己加的，用户编辑时看到也没意义，提交回来还会让 K8s 误判每次都是新版本，
            # 生成多余 ReplicaSet（影响 Deployment / StatefulSet / DaemonSet 等所有
            # 带 spec.template 的资源类型）
            spec = doc.get('spec')
            if isinstance(spec, dict):
                tmpl = spec.get('template')
                if isinstance(tmpl, dict):
                    self._strip_pod_template_hash(tmpl)
                sel = spec.get('selector')
                if isinstance(sel, dict):
                    ml = sel.get('matchLabels')
                    if isinstance(ml, dict):
                        ml.pop(self.POD_TEMPLATE_HASH_LABEL, None)
        return yaml.dump(doc, default_flow_style=False)

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
        """移除 K8s 服务端维护的只读字段，返回被剥离过的"用户感知"字段名（用于警告 UI）。

        - 创建对象时这些字段不能出现（否则 K8s 拒绝："resourceVersion should not be set on objects to be created"）
        - 更新对象时 resourceVersion 会被重新注入（用于乐观锁），其他字段保持移除
        - status 整块由 K8s 管理，apply 时不应包含 —— 改了也不会生效，必须警告用户
        """
        warnings = []
        metadata_raw = doc.get('metadata')
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        for key in (
            'resourceVersion', 'uid', 'creationTimestamp', 'generation',
            'managedFields', 'selfLink', 'deletionTimestamp',
            'deletionGracePeriodSeconds', 'ownerReferences',
        ):
            metadata.pop(key, None)
        if 'metadata' in doc and not metadata:
            doc['metadata'] = {}
        if 'status' in doc:
            warnings.append(
                'status 字段是 K8s 控制面维护的只读子资源，对它的修改不会生效，已自动忽略'
            )
            doc.pop('status', None)
        # 剥掉 spec.template / spec.selector 上的 pod-template-hash —— 这是 K8s
        # controller 自己维护的 label，用户写了反而会让 K8s 每次更新都生成新 RS，
        # 影响 Deployment / StatefulSet / DaemonSet 等所有带 spec.template 的资源
        spec_raw = doc.get('spec')
        if isinstance(spec_raw, dict):
            tmpl = spec_raw.get('template')
            if isinstance(tmpl, dict):
                tmpl_md = tmpl.get('metadata')
                if isinstance(tmpl_md, dict):
                    labels = tmpl_md.get('labels')
                    if isinstance(labels, dict):
                        labels.pop('pod-template-hash', None)
            sel = spec_raw.get('selector')
            if isinstance(sel, dict):
                ml = sel.get('matchLabels')
                if isinstance(ml, dict):
                    ml.pop('pod-template-hash', None)
        return warnings

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
            warnings = []   # 累计所有被剥离的只读字段提示，去重后随 response 返回

            for doc in docs:
                if not doc or not isinstance(doc, dict):
                    continue

                # 跟 _validate_one_doc 相同的结构防御：metadata 必须是 mapping。
                # 用户漏 ":" 后空格时 YAML 解析器把 metadata 解析成 str，
                # 不拦下来下面的 doc.get('metadata', {}).get(...) 会崩 AttributeError，
                # 在前端会以 "'str' object has no attribute 'get'" 出现，没有任何意义
                meta_raw = doc.get('metadata')
                if meta_raw is not None and not isinstance(meta_raw, dict):
                    raise Exception(
                        f'metadata 字段格式错误：解析结果是 {type(meta_raw).__name__}，'
                        f'最常见原因是 "name: xxx" 后冒号缺少空格（例如 "name:xxx" 应为 "name: xxx"）'
                    )

                kind = doc.get('kind', '').lower()
                name = (meta_raw or {}).get('name')
                namespace = (meta_raw or {}).get('namespace', 'default')

                if not kind or not name:
                    raise Exception("Invalid YAML: missing 'kind' or 'metadata.name'")

                config = self.RESOURCE_TYPES.get(kind)
                if not config:
                    raise Exception(f"Unsupported resource type: {kind}")

                doc_warnings = self._strip_server_managed_fields(doc)
                for w in doc_warnings:
                    if w not in warnings:
                        warnings.append(w)

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
                        updated = replace_method(name, namespace, doc, _request_timeout=10)
                    else:
                        updated = replace_method(name, doc, _request_timeout=10)
                    results.append(f"Updated {kind} '{name}'")

                    # 序列化最新数据返回给前端，让 markUpdated 立即用真实值刷新列表
                    # （否则前端只能等 trigger_immediate_sync 异步完成 + silent load，时序窗口里
                    #  会看到 cache 老数据，例如改完 replicas=2 还显示 1）
                    update_action = {
                        'kind': kind,
                        'name': name,
                        'namespace': namespace if config['namespaced'] else '',
                        'action': 'updated',
                    }
                    try:
                        from resources.sync_service import _serialize_item
                        update_action['resource'] = _serialize_item(kind, updated)
                    except Exception as serr:
                        logger.warning(f'Failed to serialize updated {kind} {name}: {serr}')
                    actions.append(update_action)

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

            return {
                'success': True,
                'message': '; '.join(results),
                'actions': actions,
                'warnings': warnings,
            }
        except yaml.YAMLError as e:
            return {'success': False, 'error': f'Invalid YAML: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ─── 通用 yaml 校验（server-side dry-run）──────────────────────
    # K8s schema 校验、admission webhook、配额、PSA 等所有"提交时会触发"的
    # 检查都在这里跑一遍但不真写入。比手写规则准 100 倍，且每升级一次 K8s
    # 自动获得新校验能力。
    def validate_yaml(self, yaml_content):
        """对 yaml 做 server-side dry-run，返回结构化的诊断结果。

        返回：
        {
          'success': bool,                          # 整体能否提交
          'errors':   [{kind, name, message}, ...], # K8s 拒绝的硬错误
          'warnings': [{kind, name, field, reason}, ...]
              # K8s 接受了但有副作用的提示，例如：
              # - 字段会被服务端忽略（status / resourceVersion 等）
              # - 字段不在该资源 schema 里（拼错的字段名）
              # - 用户写的值会被 K8s 默认值覆盖
          'docs': int,                              # 解析到的文档数
        }
        """
        result = {'success': True, 'errors': [], 'warnings': [], 'docs': 0}
        try:
            docs = list(yaml.safe_load_all(yaml_content))
        except yaml.YAMLError as e:
            return {
                'success': False,
                'errors': [{'kind': '-', 'name': '-', 'message': f'YAML 解析失败：{e}'}],
                'warnings': [],
                'docs': 0,
            }

        for doc in docs:
            if not doc or not isinstance(doc, dict):
                continue
            result['docs'] += 1
            self._validate_one_doc(doc, result)

        if result['errors']:
            result['success'] = False
        return result

    def _validate_one_doc(self, doc, result):
        """对单个 yaml 文档调 server-side dry-run，把结果合并进 result"""
        # 防御性结构校验：YAML 解析后顶层必须是 mapping，metadata 也必须是 mapping。
        # 用户漏了 ":" 后空格、或缩进对错位都会导致 metadata 解析成 str/list/None，
        # 后续 .get() 会崩。提前给出能看懂的报错。
        if not isinstance(doc, dict):
            result['errors'].append({'kind': '-', 'name': '-',
                'message': 'YAML 顶层结构不是 mapping，请检查缩进 / 冒号后是否漏了空格'})
            return
        meta_raw = doc.get('metadata')
        if meta_raw is not None and not isinstance(meta_raw, dict):
            result['errors'].append({'kind': str(doc.get('kind') or '-'), 'name': '-',
                'message': f'metadata 字段格式错误：解析结果是 {type(meta_raw).__name__}，'
                           f'最常见的原因是 "name: xxx" 后冒号缺少空格（例如 "name:xxx" 错，应为 "name: xxx"）'})
            return
        spec_raw = doc.get('spec')
        if spec_raw is not None and not isinstance(spec_raw, (dict, list)):
            result['errors'].append({'kind': str(doc.get('kind') or '-'), 'name': '-',
                'message': f'spec 字段格式错误：解析结果是 {type(spec_raw).__name__}，'
                           f'通常是缩进或冒号空格问题'})
            return

        kind = (doc.get('kind') or '').lower()
        meta = meta_raw or {}
        name = meta.get('name') or '-'
        namespace = meta.get('namespace') or 'default'

        if not kind:
            result['errors'].append({'kind': '-', 'name': name,
                                     'message': '缺少 kind 字段（如 Deployment / Service / ...）'})
            return
        if not meta.get('name'):
            result['errors'].append({'kind': kind, 'name': '-',
                                     'message': '缺少 metadata.name 字段'})
            return

        config = self.RESOURCE_TYPES.get(kind)
        if not config:
            result['errors'].append({
                'kind': kind, 'name': name,
                'message': f'不支持的资源类型 {kind}（仅支持：{", ".join(sorted(self.RESOURCE_TYPES.keys()))}）'
            })
            return

        # 备份用户原始 doc，dry-run 用 strip 过的 doc，回头用原始 doc 做 diff
        original_doc = copy.deepcopy(doc)
        dryrun_doc = copy.deepcopy(doc)
        self._strip_server_managed_fields(dryrun_doc)

        # 在 strip 之前先扫一遍已知"K8s 服务端保留 / 不会生效"的字段，
        # 这是显式提示，不依赖 diff（dry-run 提交的 doc 已经被剥掉这些字段，
        # diff 看不到差异）
        for path, reason in self._scan_user_facing_dropped(original_doc):
            result['warnings'].append({
                'kind': kind, 'name': name,
                'field': path,
                'reason': reason,
            })

        api_client = self._get_api_client(config['api'])

        # 判断创建/更新：先 GET，存在 → replace dry-run；不存在 → create dry-run
        existing = None
        try:
            get_method = getattr(api_client, config['get'])
            if config['namespaced']:
                existing = get_method(name, namespace, _request_timeout=5)
            else:
                existing = get_method(name, _request_timeout=5)
        except ApiException as e:
            if e.status != 404:
                # GET 都打不通就别 dry-run 了，把错误冒上去
                result['errors'].append({
                    'kind': kind, 'name': name,
                    'message': f'查询资源失败（{e.status}）：{e.reason}',
                })
                return

        try:
            applied_obj = self._dry_run_call(api_client, config, dryrun_doc, name, namespace, existing)
        except ApiException as e:
            result['errors'].append({
                'kind': kind, 'name': name,
                'message': self._humanize_api_exception(e),
            })
            return
        except Exception as e:
            result['errors'].append({'kind': kind, 'name': name, 'message': str(e)})
            return

        # dry-run 通过 —— 用户视角的"已知会被剥的字段"已经在 strip 之前 scan 过了
        # （见上面 _scan_user_facing_dropped 调用），这里不再做 diff，避免噪声警告

    def _dry_run_call(self, api_client, config, doc, name, namespace, existing):
        """根据资源是否存在选 create / replace dry-run。返回 K8s 服务端处理后的对象。"""
        # dry_run='All' 让 K8s 走完整 admission/校验链路但不真持久化
        common = {'dry_run': 'All', '_request_timeout': 10}

        if existing is None:
            # 不存在 → 创建路径
            create_name = config.get('create')
            if not create_name:
                raise Exception(f'资源类型 {config} 不支持创建')
            method = getattr(api_client, create_name)
            if config['namespaced']:
                return method(namespace, doc, **common)
            return method(doc, **common)

        # 存在 → 更新路径，注入 resourceVersion 做乐观锁
        doc.setdefault('metadata', {})
        doc['metadata']['resourceVersion'] = existing.metadata.resource_version
        replace_name = config.get('replace')
        method = getattr(api_client, replace_name)
        if config['namespaced']:
            return method(name, namespace, doc, **common)
        return method(name, doc, **common)

    @staticmethod
    def _humanize_api_exception(e):
        """把 K8s ApiException 翻译成对小白友好的错误说明。"""
        body = e.body or ''
        # 服务端通常返回 JSON 格式的 Status 对象，message 里写了人类可读原因
        try:
            import json
            obj = json.loads(body)
            msg = obj.get('message') or obj.get('reason') or e.reason
            details = obj.get('details') or {}
            causes = details.get('causes') or []
            tips = []
            for c in causes:
                t = c.get('reason') or c.get('type') or ''
                f = c.get('field') or ''
                m = c.get('message') or ''
                tips.append(f'  • [{f or t}] {m}')
            base = f'K8s 拒绝（{e.status}）：{msg}'
            if tips:
                base += '\n' + '\n'.join(tips)
            # 在 base 之外补一条"普通用户能看懂"的归因
            hint = K8sResourceManager._classify_error(e.status, msg)
            if hint:
                base += f'\n💡 {hint}'
            return base
        except Exception:
            return f'K8s 拒绝（{e.status}）：{e.reason}：{body[:300]}'

    @staticmethod
    def _classify_error(status, msg):
        """常见错误的"小白解释" —— 解释为什么会发生，怎么改"""
        m = (msg or '').lower()
        if status == 422 or 'invalid' in m:
            if 'immutable' in m or 'cannot be changed' in m or 'forbidden' in m and 'updates to' in m:
                return ('该字段在资源创建后不可更改（K8s 不可变字段，如 Service.spec.clusterIP、'
                        'PVC.spec.storageClassName、Pod 的大部分 spec 字段等）。如需变更请删除后重建。')
            if 'required value' in m or 'must be specified' in m:
                return '缺少必填字段，请按 K8s 文档补全后重试。'
            if 'invalid value' in m:
                return '某个字段的值不合法（格式 / 取值范围错误），请按上方 [field] 提示修正。'
            return '资源校验失败，请按上方 [field] 修复'
        if status == 409:
            return '资源版本冲突或已存在。可能是别人/控制器同时改动了，请重新打开 YAML 拿最新版本再试。'
        if status == 403:
            return '当前 kubeconfig 没有这个操作的权限（403 Forbidden）。'
        if status == 404:
            return '关联的对象不存在（如引用了不存在的 namespace / serviceaccount / pvc）。'
        if status == 400 and 'unknown field' in m:
            return ('YAML 里有 K8s schema 不认识的字段（拼写错？版本错？）。'
                    '请检查字段名大小写以及 apiVersion 是否匹配。')
        return None

    @staticmethod
    def _scan_user_facing_dropped(doc):
        """从用户原始 doc 里挑出"我们一定会剥掉、用户应该知道这点"的字段路径。

        与 _strip_server_managed_fields 的字段集合保持一致；这是给用户看的提示，
        所以只挑用户视角"看得懂"的高频项，不刷屏。
        """
        out = []
        if not isinstance(doc, dict):
            return out
        if 'status' in doc:
            out.append(('status',
                'status 是 K8s 控制面维护的只读子资源，对它的修改会被服务端静默忽略。'
                '要影响资源运行状态请改 spec/template 触发控制器调谐。'))
        meta_raw = doc.get('metadata')
        meta = meta_raw if isinstance(meta_raw, dict) else {}
        readonly_meta = {
            'resourceVersion': 'K8s 内部用于乐观锁，由服务端维护，写了也无效',
            'uid': 'K8s 自动生成的全局唯一 ID，不可写',
            'creationTimestamp': '资源创建时间，由服务端写入，不可改',
            'generation': 'spec 变更次数，由服务端维护',
            'managedFields': 'server-side apply 的字段所有权记录，不该手工写',
            'selfLink': '已弃用字段',
            'deletionTimestamp': '资源被删除时由服务端写入，不可手动设置',
            'ownerReferences': '由控制器维护（如 ReplicaSet → Pod 的 owner），手工写会被覆盖',
        }
        for k, why in readonly_meta.items():
            if k in meta:
                out.append((f'metadata.{k}', why))
        return out

        """对 diff 出来的"被丢字段"给一个说人话的解释。返回 None 表示不值得告诉用户。"""
        # 顶层 status：永远是控制面只读的
        if path == 'status' or path.startswith('status.'):
            return ('status 是 K8s 控制面维护的只读子资源，对它的修改会被服务端静默忽略。'
                    '要改资源的运行状态请改 spec/template 触发控制器调谐。')
        # metadata 下的服务端字段
        readonly_meta = {
            'metadata.resourceVersion': 'K8s 内部用于乐观锁，由服务端维护，写了也无效',
            'metadata.uid': 'K8s 自动生成的全局唯一 ID，不可写',
            'metadata.creationTimestamp': '资源创建时间，由服务端写入，不可改',
            'metadata.generation': 'spec 变更次数，由服务端维护',
            'metadata.managedFields': 'server-side apply 的字段所有权记录，不该手工写',
            'metadata.selfLink': '已弃用字段',
            'metadata.deletionTimestamp': '资源被删除时由服务端写入，不可手动设置',
            'metadata.ownerReferences': '由控制器维护（如 ReplicaSet → Pod 的 owner），手工写会被覆盖',
        }
        if path in readonly_meta:
            return readonly_meta[path]
        # 其他字段被丢一般是 schema 不认识或 server-side default
        # 不是所有 dropped 都值得提示，避免警告刷屏
        return None

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

    # ─── Describe / Events / 关联 Pod ───────────────────────────
    @staticmethod
    def _ts_to_str(ts):
        return ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '-'

    def _list_events_for(self, namespace, kind, name, uid=None):
        """查 involvedObject 是 (kind,name) 的 events，按时间倒序"""
        try:
            field_selector = f'involvedObject.kind={kind},involvedObject.name={name}'
            if uid:
                field_selector += f',involvedObject.uid={uid}'
            evs = self.core_v1.list_namespaced_event(
                namespace, field_selector=field_selector, _request_timeout=10
            )
        except ApiException as e:
            logger.warning(f'list events for {kind}/{name} failed: {e.reason}')
            return []

        out = []
        for e in evs.items:
            ts = e.last_timestamp or e.event_time or e.first_timestamp or e.metadata.creation_timestamp
            out.append({
                'type': e.type or '-',
                'reason': e.reason or '-',
                'message': e.message or '',
                'source': (e.source.component if e.source else '') or '-',
                'count': e.count or 1,
                'last_timestamp': self._ts_to_str(ts),
                '_sort_key': ts.timestamp() if ts else 0,
            })
        out.sort(key=lambda x: x['_sort_key'], reverse=True)
        for o in out:
            o.pop('_sort_key', None)
        return out

    def _list_pods_by_selector(self, namespace, match_labels):
        """按 label selector 拉取 namespace 下的 pods（仅支持 matchLabels）"""
        if not match_labels:
            return []
        label_selector = ','.join(f'{k}={v}' for k, v in match_labels.items())
        try:
            res = self.core_v1.list_namespaced_pod(
                namespace, label_selector=label_selector, _request_timeout=15
            )
        except ApiException as e:
            logger.warning(f'list pods by selector failed: {e.reason}')
            return []

        from resources.sync_service import _serialize_item
        return [_serialize_item('pod', p) for p in res.items]

    def describe_deployment(self, name, namespace):
        """汇总 Deployment 的状态/conditions/events/关联 Pods，给前端 describe modal"""
        try:
            dep = self.apps_v1.read_namespaced_deployment(name, namespace, _request_timeout=10)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"Deployment '{name}' not found in namespace '{namespace}'")
            raise Exception(f"Failed to read deployment: {e.reason}")

        spec = dep.spec
        status = dep.status
        meta = dep.metadata

        strategy_obj = spec.strategy if spec else None
        strategy = {
            'type': strategy_obj.type if strategy_obj else '-',
        }
        if strategy_obj and strategy_obj.rolling_update:
            ru = strategy_obj.rolling_update
            strategy['max_surge'] = str(ru.max_surge) if ru.max_surge is not None else '-'
            strategy['max_unavailable'] = str(ru.max_unavailable) if ru.max_unavailable is not None else '-'

        match_labels = {}
        if spec and spec.selector and spec.selector.match_labels:
            match_labels = dict(spec.selector.match_labels)

        containers = []
        if spec and spec.template and spec.template.spec:
            for c in spec.template.spec.containers or []:
                containers.append({
                    'name': c.name,
                    'image': c.image or '-',
                    'ports': [f'{p.container_port}/{p.protocol or "TCP"}' for p in (c.ports or [])],
                })

        conditions = []
        for c in (status.conditions or []) if status else []:
            conditions.append({
                'type': c.type,
                'status': c.status,
                'reason': c.reason or '-',
                'message': c.message or '',
                'last_update': self._ts_to_str(c.last_update_time),
            })

        info = {
            'name': meta.name,
            'namespace': meta.namespace,
            'created': self._ts_to_str(meta.creation_timestamp),
            'labels': dict(meta.labels or {}),
            'annotations': {k: v for k, v in (meta.annotations or {}).items() if not k.startswith('kubectl.kubernetes.io/last-applied')},
            'replicas': spec.replicas or 0,
            'ready_replicas': (status.ready_replicas if status else None) or 0,
            'available_replicas': (status.available_replicas if status else None) or 0,
            'updated_replicas': (status.updated_replicas if status else None) or 0,
            'unavailable_replicas': (status.unavailable_replicas if status else None) or 0,
            'strategy': strategy,
            'selector': match_labels,
            'containers': containers,
            'observed_generation': (status.observed_generation if status else None) or 0,
            'generation': meta.generation or 0,
        }

        return {
            'info': info,
            'conditions': conditions,
            'events': self._list_events_for(namespace, 'Deployment', name, meta.uid),
            'pods': self._list_pods_by_selector(namespace, match_labels),
        }

    # ─── Rollout 历史 / 回滚 ─────────────────────────────────────
    REVISION_ANNOTATION = 'deployment.kubernetes.io/revision'
    CHANGE_CAUSE_ANNOTATION = 'kubernetes.io/change-cause'

    def list_deployment_revisions(self, name, namespace):
        """列出 deployment 的 ReplicaSet 历史，按 revision 倒序"""
        try:
            dep = self.apps_v1.read_namespaced_deployment(name, namespace, _request_timeout=10)
        except ApiException as e:
            raise Exception(f"Failed to read deployment: {e.reason}")

        match_labels = {}
        if dep.spec and dep.spec.selector and dep.spec.selector.match_labels:
            match_labels = dict(dep.spec.selector.match_labels)
        if not match_labels:
            return {'current_revision': None, 'revisions': []}

        label_selector = ','.join(f'{k}={v}' for k, v in match_labels.items())
        try:
            # 不带 selector 全量拉取该 ns 下所有 RS —— 让 owner_references 来过滤更可靠：
            # 用 deployment.spec.selector 做 label_selector 看似精准，但用户若手改过 yaml
            # 删掉了 RS 的 selector match label，就会漏掉旧 RS。owner_references 是 controller
            # 自己维护的、不依赖业务 label，可靠性更高。
            rs_list = self.apps_v1.list_namespaced_replica_set(
                namespace, _request_timeout=15
            )
        except ApiException as e:
            raise Exception(f"Failed to list replica sets: {e.reason}")

        # 仅保留 ownerReferences 指向当前 deployment 的 RS
        owned = []
        for rs in rs_list.items:
            for owner in (rs.metadata.owner_references or []):
                if owner.kind == 'Deployment' and owner.name == name:
                    owned.append(rs)
                    break

        logger.info(
            f'[rollout-history] deployment={namespace}/{name} '
            f'total_rs_in_ns={len(rs_list.items)} owned_by_deploy={len(owned)} '
            f'selector={match_labels}'
        )

        current_rev = (dep.metadata.annotations or {}).get(self.REVISION_ANNOTATION)
        revisions = []
        for rs in owned:
            ann = rs.metadata.annotations or {}
            rev = ann.get(self.REVISION_ANNOTATION)
            if not rev:
                logger.info(f'[rollout-history] rs={rs.metadata.name} skipped (no revision annotation)')
                continue
            containers = (rs.spec.template.spec.containers
                          if rs.spec and rs.spec.template and rs.spec.template.spec else []) or []
            revisions.append({
                'revision': rev,
                'rs_name': rs.metadata.name,
                'images': [c.image for c in containers if c.image],
                'change_cause': ann.get(self.CHANGE_CAUSE_ANNOTATION, ''),
                'created': self._ts_to_str(rs.metadata.creation_timestamp),
                'replicas': rs.spec.replicas if rs.spec else 0,
                'is_current': str(rev) == str(current_rev),
            })

        revisions.sort(key=lambda r: int(r['revision']), reverse=True)
        return {'current_revision': current_rev, 'revisions': revisions}

    # ReplicaSet 上 controller 自己维护的 pod-template-hash label。
    # 回滚 / 复制 RS template 时必须剥掉它，否则 K8s 会把它当用户写的 label 跟
    # 新算的 hash 一起塞进新 RS，导致每次回滚都生成一个新 RS（revision 一直涨）。
    # kubectl rollout undo 也是同样的处理。
    POD_TEMPLATE_HASH_LABEL = 'pod-template-hash'

    @classmethod
    def _strip_pod_template_hash(cls, template):
        """从 spec.template 上剥掉 controller-owned 的 pod-template-hash label。

        template 可以是 V1PodTemplateSpec 对象，也可以是 dict（apply_yaml 的场景）。
        直接修改入参，无返回值。
        """
        if template is None:
            return
        # SDK 对象路径
        meta = getattr(template, 'metadata', None)
        if meta is not None:
            labels = getattr(meta, 'labels', None)
            if isinstance(labels, dict):
                labels.pop(cls.POD_TEMPLATE_HASH_LABEL, None)
            return
        # dict 路径（apply_yaml 解析的 yaml doc）
        if isinstance(template, dict):
            md = template.get('metadata')
            if isinstance(md, dict):
                labels = md.get('labels')
                if isinstance(labels, dict):
                    labels.pop(cls.POD_TEMPLATE_HASH_LABEL, None)

    def rollback_deployment(self, name, namespace, target_revision):
        """把 deployment 的 spec.template 回滚到指定 revision 对应的 ReplicaSet template。

        关键：必须用 replace（PUT 整个对象）而不是 patch。
        K8s strategic merge patch 对 containers[].ports / env 这种 list 是按 merge key 合并，
        只能"加项"不能"删项"——会出现回滚后端口越来越多的诡异现象。
        replace 是整对象覆盖，没有 merge 语义，等价于 kubectl replace。
        """
        target_rev = str(target_revision)
        try:
            dep = self.apps_v1.read_namespaced_deployment(name, namespace, _request_timeout=10)
        except ApiException as e:
            raise Exception(f"Failed to read deployment: {e.reason}")

        try:
            # 全量拉 RS 用 owner_references 过滤，比 selector label 可靠
            rs_list = self.apps_v1.list_namespaced_replica_set(namespace, _request_timeout=15)
        except ApiException as e:
            raise Exception(f"Failed to list replica sets: {e.reason}")

        target_rs = None
        for rs in rs_list.items:
            owners = rs.metadata.owner_references or []
            if not any(o.kind == 'Deployment' and o.name == name for o in owners):
                continue
            ann_rev = (rs.metadata.annotations or {}).get(self.REVISION_ANNOTATION)
            if str(ann_rev) == target_rev:
                target_rs = rs
                break

        if target_rs is None:
            raise Exception(f"Revision {target_rev} not found")

        current_rev = (dep.metadata.annotations or {}).get(self.REVISION_ANNOTATION)
        if str(current_rev) == target_rev:
            raise Exception(f"Already at revision {target_rev}, no rollback needed")

        # 整体替换 spec.template；剥掉旧 RS 的 pod-template-hash label——
        # 这是 controller 自己加的，不剥的话 K8s 会把它当用户 label，每次回滚都
        # 生成一个新 RS（revision 一直涨，即便实质内容一致）
        dep.spec.template = target_rs.spec.template
        self._strip_pod_template_hash(dep.spec.template)

        if dep.metadata.annotations is None:
            dep.metadata.annotations = {}
        dep.metadata.annotations[self.CHANGE_CAUSE_ANNOTATION] = f'Rollback to revision {target_rev}'

        # managed_fields 在 replace 时如果带上可能引发 server 端 conflict，去掉更稳
        if hasattr(dep.metadata, 'managed_fields'):
            dep.metadata.managed_fields = None

        try:
            self.apps_v1.replace_namespaced_deployment(
                name, namespace, dep, _request_timeout=15
            )
        except ApiException as e:
            raise Exception(f"Failed to rollback deployment: {e.reason}")
