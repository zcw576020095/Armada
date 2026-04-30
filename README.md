# Armada

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-6.0.4-092E20?logo=django&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Client_v35-326CE5?logo=kubernetes&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4.2-38B2AC?logo=tailwindcss&logoColor=white)
![DaisyUI](https://img.shields.io/badge/DaisyUI-5.5-5A0EF8?logo=daisyui&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-Ready-E6522C?logo=prometheus&logoColor=white)
![License](https://img.shields.io/badge/License-Private-red)
![Platform](https://img.shields.io/badge/Platform-Linux_|_macOS_|_Windows-lightgrey)

> 告别 kubectl 命令行切换之苦 —— 一个面板管理你所有的 Kubernetes 集群

Armada 是一个专业的 Web 端 Kubernetes 多集群管理面板，具备现代化商务风格 UI、细粒度用户权限控制、实时资源同步和集成监控等功能。

---

## 功能特性

### 多集群管理
- 通过 kubeconfig 添加/导入 Kubernetes 集群
- 查看集群详情（版本、API Server、节点数量、状态）
- 编辑集群显示名称、描述和 kubeconfig
- 后台刷新集群信息

### 仪表盘 & 监控
- **接入 Prometheus 时**：CPU/内存使用率图表、节点指标热力图、GPU 节点统计
- **未接入 Prometheus 时**：节点容量概览、资源分配展示
- 集群健康状态实时指示

### 资源管理
全面管理核心 K8s 资源类型：

| 分类 | 资源 |
|------|------|
| **工作负载** | Deployments、StatefulSets、DaemonSets、Pods |
| **网络** | Services、Ingresses |
| **配置** | ConfigMaps、Secrets |
| **存储** | PersistentVolumeClaims |
| **命名空间** | Namespace 管理 |

支持的操作：
- **查看**：列表展示、YAML 查看、资源详情
- **编辑**：在线 YAML 编辑、一键扩缩容（Deployments/StatefulSets）、ConfigMap/Secret 修改
- **操作**：重启、删除、Cordon/Uncordon/Drain（节点）
- **日志**：Pod 实时日志流查看
- **终端**：Pod 终端直连（exec 进入容器，免 kubectl）

### 用户与权限管理
- **基于角色的访问控制**：管理员（Admin）和普通用户（User）两种角色
- **模块级权限控制**：按集群按模块进行细粒度权限管理（共 13 个模块）
  - Dashboard、Cluster、Node、Deployment、StatefulSet、DaemonSet、Pod、Service、Ingress、ConfigMap、Secret、PVC、Namespace
- **权限类型**：查看（只读）或编辑（完全控制，包括删除）
- 基于 Session 的认证机制，自定义中间件强制权限校验

### 技术亮点
- **Kubeconfig 加密存储**（Fernet 加密）
- **后台资源同步**：守护线程每 60 秒同步 K8s 资源
- **本地数据库缓存**：资源加载速度比直接调用 K8s API 快 100 倍以上
- **Prometheus 集成**：可选指标监控，优雅降级
- **AJAX 动态加载**：轻量 HTML 骨架 + JSON API

---

## 功能截图

> 截图集中存放在 [`docs/screenshots/`](docs/screenshots/)，命名规范见该目录的 [README](docs/screenshots/README.md)。

### 登录与权限

| 登录页 | 用户管理 | 权限管理 |
|:---:|:---:|:---:|
| ![登录页](docs/screenshots/login.png) | ![用户管理](docs/screenshots/users.png) | ![权限管理](docs/screenshots/permissions.png) |
| 支持账户禁用提示 / 密码显隐切换 / CSRF 失效友好回登录 | 管理员 / 普通用户两种角色 | 按集群 × 模块的细粒度权限 |

### 集群与节点

| 集群列表 | 新增集群 | 节点管理 |
|:---:|:---:|:---:|
| ![集群列表](docs/screenshots/clusters-list.png) | ![新增集群](docs/screenshots/cluster-add.png) | ![节点管理](docs/screenshots/nodes.png) |
| 多集群一键切换 | kubeconfig 加密存储 | Cordon / Uncordon / Drain |

### 仪表盘

![仪表盘](docs/screenshots/dashboard.png)

接入 Prometheus 时展示 CPU / 内存 / GPU 节点指标；未接入时优雅降级到节点容量概览。

### 资源管理

| Deployment 列表 | Deployment 详情 | 回滚到历史版本 |
|:---:|:---:|:---:|
| ![Deployment 列表](docs/screenshots/deployments.png) | ![Deployment 详情](docs/screenshots/deployment-detail.png) | ![Deployment 回滚](docs/screenshots/deployment-rollback.png) |
| 详情 / YAML / 扩缩 / 重启 / 回滚 / 删除 | 概览 + Events + 关联 Pods | 列出所有 ReplicaSet 历史，一键回滚 |

| 命名空间 | 扩缩容 | 删除级联警告 |
|:---:|:---:|:---:|
| ![命名空间](docs/screenshots/namespaces.png) | ![扩缩容](docs/screenshots/deployment-scale.png) | ![删除 ns](docs/screenshots/namespace-delete.png) |

| Pod 列表 | Pod 实时日志 | Pod 终端 exec |
|:---:|:---:|:---:|
| ![Pod 列表](docs/screenshots/pods.png) | ![Pod 日志](docs/screenshots/pod-logs.png) | ![Pod 终端](docs/screenshots/pod-exec.png) |
| 容器层卡点 reason 高亮（ImagePullBackOff 等） | 实时刷新 / 上次日志 / tail 行数 | 浏览器内直连容器 shell |

| StatefulSets | DaemonSets | Services |
|:---:|:---:|:---:|
| ![StatefulSets](docs/screenshots/statefulsets.png) | ![DaemonSets](docs/screenshots/daemonsets.png) | ![Services](docs/screenshots/services.png) |

| Ingresses | ConfigMaps | Secrets / PVC |
|:---:|:---:|:---:|
| ![Ingresses](docs/screenshots/ingresses.png) | ![ConfigMaps](docs/screenshots/configmaps.png) | ![Secrets](docs/screenshots/secrets.png) |

### YAML 编辑与校验

| YAML 编辑（默认只读） | "+ 新建" 通过模板创建 | server-side dry-run 校验 |
|:---:|:---:|:---:|
| ![YAML 编辑](docs/screenshots/yaml-edit.png) | ![YAML 新建](docs/screenshots/yaml-create.png) | ![YAML 校验](docs/screenshots/yaml-validate.png) |
| 默认只读预览，按"编辑模式"开关切换 | 每种资源预填模板 | 调 K8s 真实 dry-run，错误翻译成中文带 💡 解释 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Django 6.0.4 |
| 数据库 | SQLite |
| K8s 集成 | Kubernetes Python Client v35.0.0 |
| 监控 | Prometheus（可选） |
| 前端 | Django Templates + Alpine.js |
| CSS 框架 | Tailwind CSS 4.2.2 + DaisyUI 5.5.19 |
| 图标 | FontAwesome |
| 加密 | Fernet（cryptography） |
| 构建工具 | @tailwindcss/cli |

---

## 安装部署

### 环境要求
- Python 3.10+
- Node.js 18+（用于 Tailwind CSS 编译）
- 可用的 Kubernetes 集群及 kubeconfig

### 安装步骤

1. **克隆并进入项目目录**
   ```bash
   cd Armada
   ```

2. **安装 Python 依赖**
   ```bash
   pip install django==6.0.4 kubernetes==35.0.0 pyyaml python-dateutil cryptography prometheus-client
   ```

3. **安装 Node 依赖**
   ```bash
   npm install
   ```

4. **编译 Tailwind CSS**
   ```bash
   npx @tailwindcss/cli -i ./static/css/input.css -o ./static/css/output.css --watch
   ```

5. **初始化数据库**
   ```bash
   python manage.py migrate
   ```

6. **创建管理员账户**
   ```bash
   python manage.py createsuperuser
   ```

7. **启动开发服务器**
   ```bash
   python manage.py runserver
   ```

8. **访问面板**
   浏览器打开 [http://localhost:8000](http://localhost:8000)

---

## 项目结构

```
Armada/
├── armada/                    # Django 项目配置
│   ├── settings.py           # 主配置文件
│   └── urls.py               # 根路由配置
├── clusters/                 # 集群管理应用
│   ├── models.py             # 集群模型
│   ├── views.py              # 集群视图
│   ├── k8s_client.py         # K8s 客户端连接池
│   └── prometheus.py         # Prometheus 指标集成
├── resources/                # K8s 资源管理应用
│   ├── models.py             # 资源缓存模型
│   ├── views.py              # 资源 CRUD 视图
│   ├── k8s_resources.py      # 资源管理器
│   └── sync_service.py       # 后台同步服务
├── dashboard/                # 仪表盘应用
│   └── views.py              # 仪表盘视图
├── accounts/                 # 用户与认证应用
│   ├── models.py             # 用户资料、权限模型
│   ├── views.py              # 认证与用户管理
│   └── middleware.py         # 权限校验中间件
├── templates/                # Django HTML 模板
├── static/
│   ├── css/                  # 编译后的 Tailwind CSS
│   ├── js/                   # JavaScript 文件
│   └── webfonts/             # FontAwesome 字体
├── manage.py                 # Django 命令行工具
├── package.json              # Node.js 依赖
└── design_plan.md            # UI 重设计文档
```

---

## API 路由

### 集群管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/clusters/` | 集群列表 |
| POST | `/clusters/add/` | 添加集群 |
| GET | `/clusters/<id>/` | 集群详情 |
| POST | `/clusters/<id>/edit/` | 编辑集群 |
| POST | `/clusters/<id>/delete/` | 删除集群 |
| POST | `/clusters/<id>/refresh/` | 刷新集群信息 |
| GET | `/clusters/<id>/nodes/` | 节点管理 |
| POST | `/clusters/<id>/node/<name>/cordon/` | 隔离节点 |
| POST | `/clusters/<id>/node/<name>/uncordon/` | 取消隔离 |
| POST | `/clusters/<id>/node/<name>/drain/` | 驱逐节点 |

### 资源管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/resources/<id>/namespaces/` | 命名空间列表 |
| POST | `/resources/<id>/namespaces/create/` | 创建命名空间 |
| GET | `/resources/<id>/deployments/` | Deployment 列表 |
| POST | `/resources/<id>/deployments/<ns>/<name>/scale/` | 扩缩容 |
| POST | `/resources/<id>/deployments/<ns>/<name>/restart/` | 重启 |
| GET | `/resources/<id>/pods/` | Pod 列表 |
| GET | `/resources/<id>/pods/<ns>/<name>/logs/` | 查看日志 |
| GET | `/resources/<id>/services/` | Service 列表 |
| GET | `/resources/<id>/ingresses/` | Ingress 列表 |
| GET | `/resources/<id>/configmaps/` | ConfigMap 列表 |
| GET | `/resources/<id>/secrets/` | Secret 列表 |
| GET | `/resources/<id>/pvcs/` | PVC 列表 |
| GET | `/resources/<id>/yaml/<type>/<ns>/<name>/` | 获取资源 YAML |
| POST | `/resources/<id>/delete/<type>/<ns>/<name>/` | 删除资源 |

### 账户管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/accounts/login/` | 登录页 |
| POST | `/accounts/login/` | 登录 |
| GET | `/accounts/logout/` | 登出 |
| GET | `/accounts/profile/` | 个人资料 |
| GET | `/accounts/users/` | 用户列表（管理员） |
| POST | `/accounts/users/create/` | 创建用户（管理员） |
| POST | `/accounts/users/<id>/delete/` | 删除用户（管理员） |
| GET | `/accounts/permissions/` | 权限列表（管理员） |
| POST | `/accounts/permissions/create/` | 创建权限（管理员） |

---

## 配置说明

### 集群配置
添加集群时需要提供：
- **显示名称**：集群的友好名称
- **描述**：可选描述信息
- **Prometheus URL**：可选（如 `http://prometheus-server:9090`）
- **Kubeconfig**：粘贴完整的 kubeconfig YAML（存储前会加密）

### 权限配置
为用户分配按集群按模块的权限：
- 选择用户和集群
- 选择模块（如 `deployment`、`pod`、`configmap`）
- 设置权限类型：`view`（查看）或 `edit`（编辑）

---

## 许可证

私有项目，保留所有权利。
