# 截图目录

本目录存放 Armada 平台的功能截图，用于在项目 README 中展示功能。

## 命名规范

为了让 README 引用稳定且一目了然，请按如下规范命名截图文件（小写 + 连字符，按"功能模块-子功能"组织）：

| 文件名 | 对应功能 |
|---|---|
| `login.png` | 登录页 |
| `dashboard.png` | 仪表盘 / 集群概览 |
| `clusters-list.png` | 集群列表 |
| `cluster-add.png` | 新增集群（kubeconfig） |
| `nodes.png` | 节点管理 |
| `namespaces.png` | 命名空间列表 |
| `namespace-delete.png` | 删除命名空间（级联警告） |
| `deployments.png` | Deployment 列表 |
| `deployment-detail.png` | Deployment 详情 modal（概览 / Events / 关联 Pods） |
| `deployment-rollback.png` | Deployment 回滚（ReplicaSet 历史） |
| `deployment-scale.png` | Deployment 扩缩容 |
| `statefulsets.png` | StatefulSet 列表 |
| `daemonsets.png` | DaemonSet 列表 |
| `pods.png` | Pod 列表（状态 + 容器层卡点 reason） |
| `pod-logs.png` | Pod 实时日志 |
| `pod-exec.png` | Pod 终端 exec |
| `services.png` | Service 列表 |
| `ingresses.png` | Ingress 列表 |
| `configmaps.png` | ConfigMap 列表 |
| `secrets.png` | Secret 列表 |
| `pvcs.png` | PVC 列表 |
| `yaml-edit.png` | YAML 编辑器（默认只读 / 编辑模式开关） |
| `yaml-create.png` | "+ 新建" 通过 YAML 模板创建资源 |
| `yaml-validate.png` | YAML 校验（K8s server-side dry-run，错误中文翻译） |
| `users.png` | 用户管理 |
| `permissions.png` | 权限管理（按集群按模块） |

## 添加新截图

1. 截图保存为 PNG 格式（推荐 1440×900 或 retina 2x）
2. 文件名按上表，小写 + 连字符
3. 放进本目录
4. 在 `README.md` 的「功能截图」章节用 `![描述](docs/screenshots/xxx.png)` 引用即可

GitHub 会自动渲染相对路径的图片，无需任何配置。
