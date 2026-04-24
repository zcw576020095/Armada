# Armada 下一阶段功能规划

## 阶段 2：核心功能补全

### 1. Events 查看器
**优先级：高**

#### 功能描述
- 显示集群事件（Warning/Normal）
- 按资源类型过滤事件
- 按命名空间过滤
- 实时更新事件流
- 事件详情展示（Message、Reason、Source、Count）

#### 技术实现
- 后端：`resources/views.py` 添加 `events_list_api()`
- 使用 `core_v1.list_event_for_all_namespaces()`
- 数据库缓存：`K8sResourceCache` 存储事件（TTL 30秒，事件变化快）
- 前端：`templates/resources/event_list.html`
- 颜色编码：Warning=红色，Normal=绿色

#### 预计工作量
- 后端：2-3 小时
- 前端：1-2 小时

---

### 2. 资源详情页
**优先级：高**

#### 功能描述
- **Pod 详情页**
  - 基本信息：Name、Namespace、Status、Node、IP、QoS Class
  - Conditions：Ready、Initialized、ContainersReady、PodScheduled
  - Containers：Image、Ports、Resources (Requests/Limits)、Environment Variables
  - Volumes：挂载的 Volume 列表
  - Events：该 Pod 相关的事件
  - 操作按钮：查看日志、进入 Shell、删除

- **Deployment 详情页**
  - 基本信息：Replicas、Strategy、Selector
  - ReplicaSet 历史：显示所有 RS 及其版本
  - Conditions：Available、Progressing
  - Pod 列表：该 Deployment 管理的所有 Pod
  - Events：该 Deployment 相关的事件

- **Service 详情页**
  - 基本信息：Type、Cluster IP、External IP、Ports
  - Endpoints：后端 Pod 列表
  - Selector：标签选择器
  - Events

#### 技术实现
- 后端：`resources/views.py` 添加 `pod_detail()`, `deployment_detail()` 等
- 使用 `core_v1.read_namespaced_pod()` 获取详情
- 前端：`templates/resources/pod_detail.html` 等
- URL 路由：`/resources/<pk>/pods/<ns>/<name>/detail/`

#### 预计工作量
- 后端：4-6 小时（每种资源 1-2 小时）
- 前端：6-8 小时（每种资源 2 小时）

---

### 3. 实时日志流
**优先级：中**

#### 功能描述
- WebSocket 实时推送日志
- 自动滚动到底部
- 暂停/恢复自动滚动
- 下载日志文件
- 多容器切换（Pod 有多个容器时）

#### 技术实现
- 后端：Django Channels + WebSocket
- 使用 `core_v1.read_namespaced_pod_log(follow=True, _preload_content=False)`
- 流式读取日志并通过 WebSocket 推送
- 前端：WebSocket 客户端，接收日志并追加到 `<pre>` 标签

#### 依赖
- 需要安装 `channels`, `daphne`
- 修改 `settings.py` 添加 ASGI 配置

#### 预计工作量
- 后端：4-6 小时
- 前端：2-3 小时

---

### 4. Exec/Shell (Web Terminal)
**优先级：中**

#### 功能描述
- 在浏览器中进入 Pod 的 Shell
- 支持 bash/sh 切换
- 支持多容器选择
- 终端大小自适应
- 复制粘贴支持

#### 技术实现
- 后端：Django Channels + WebSocket
- 使用 `stream()` API 连接 Pod 的 exec
- 双向通信：浏览器 ↔ Django ↔ K8s API
- 前端：xterm.js 终端模拟器

#### 依赖
- `channels`, `daphne`
- `xterm.js` (CDN 或本地)

#### 预计工作量
- 后端：6-8 小时（WebSocket + K8s stream 复杂）
- 前端：3-4 小时

---

### 5. CronJob/Job 管理
**优先级：中**

#### 功能描述
- **CronJob**
  - 列表：Name、Schedule、Suspend、Active、Last Schedule
  - 详情：显示关联的 Job 列表
  - 操作：暂停/恢复、手动触发、删除

- **Job**
  - 列表：Name、Completions、Duration、Age
  - 详情：显示关联的 Pod 列表
  - 操作：查看日志、删除

#### 技术实现
- 后端：`resources/views.py` 添加 `cronjob_list_api()`, `job_list_api()`
- 使用 `batch_v1.list_cron_job_for_all_namespaces()`
- 数据库缓存：`sync_service.py` 添加 CronJob/Job 同步
- 前端：`templates/resources/cronjob_list.html`, `job_list.html`

#### 预计工作量
- 后端：3-4 小时
- 前端：2-3 小时

---

### 6. HPA (Horizontal Pod Autoscaler)
**优先级：低**

#### 功能描述
- 列表：Name、Reference、Min/Max Replicas、Current Replicas、Targets
- 创建 HPA：选择 Deployment/StatefulSet，设置 CPU/Memory 阈值
- 编辑 HPA：修改副本数和阈值
- 删除 HPA

#### 技术实现
- 后端：`resources/views.py` 添加 `hpa_list_api()`, `hpa_create()`, `hpa_delete()`
- 使用 `autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces()`
- 前端：`templates/resources/hpa_list.html`

#### 预计工作量
- 后端：4-5 小时
- 前端：3-4 小时

---

### 7. StorageClass/PV 管理
**优先级：低**

#### 功能描述
- **StorageClass**
  - 列表：Name、Provisioner、Reclaim Policy、Volume Binding Mode
  - 详情：显示使用该 SC 的 PVC 列表
  - 操作：查看 YAML、删除

- **PersistentVolume (PV)**
  - 列表：Name、Capacity、Access Modes、Reclaim Policy、Status、Claim
  - 详情：显示绑定的 PVC
  - 操作：查看 YAML、删除

#### 技术实现
- 后端：`resources/views.py` 添加 `storageclass_list_api()`, `pv_list_api()`
- 使用 `storage_v1.list_storage_class()`, `core_v1.list_persistent_volume()`
- 前端：`templates/resources/storageclass_list.html`, `pv_list.html`

#### 预计工作量
- 后端：3-4 小时
- 前端：2-3 小时

---

### 8. RBAC 管理
**优先级：低**

#### 功能描述
- **ServiceAccount**
  - 列表：Name、Namespace、Secrets
  - 创建/删除

- **Role/ClusterRole**
  - 列表：Name、Namespace (Role only)
  - 详情：显示 Rules (API Groups、Resources、Verbs)
  - 操作：查看 YAML、删除

- **RoleBinding/ClusterRoleBinding**
  - 列表：Name、Role、Subjects
  - 详情：显示绑定关系
  - 操作：查看 YAML、删除

#### 技术实现
- 后端：`resources/views.py` 添加 RBAC 相关 API
- 使用 `rbac_authorization_v1` API
- 前端：`templates/resources/rbac_*.html`

#### 预计工作量
- 后端：6-8 小时（RBAC 复杂）
- 前端：4-6 小时

---

### 9. Network Policy 管理
**优先级：低**

#### 功能描述
- 列表：Name、Namespace、Pod Selector、Policy Types
- 详情：显示 Ingress/Egress 规则
- 操作：查看 YAML、删除

#### 技术实现
- 后端：`resources/views.py` 添加 `networkpolicy_list_api()`
- 使用 `networking_v1.list_network_policy_for_all_namespaces()`
- 前端：`templates/resources/networkpolicy_list.html`

#### 预计工作量
- 后端：2-3 小时
- 前端：2-3 小时

---

### 10. 资源使用趋势图
**优先级：低**

#### 功能描述
- 集群级别：CPU/Memory 使用趋势（过去 1h/6h/24h/7d）
- 节点级别：每个节点的资源使用趋势
- Pod 级别：单个 Pod 的资源使用趋势
- 使用 ECharts 折线图展示

#### 技术实现
- 后端：集成 Prometheus
- 使用 PromQL 查询历史数据
- `clusters/prometheus.py` 添加趋势查询方法
- 前端：ECharts 折线图

#### 依赖
- 集群需要部署 Prometheus
- 需要配置 Prometheus URL

#### 预计工作量
- 后端：6-8 小时（Prometheus 集成）
- 前端：4-5 小时

---

## 总预计工作量

| 功能 | 优先级 | 后端 | 前端 | 总计 |
|------|--------|------|------|------|
| Events 查看器 | 高 | 2-3h | 1-2h | 3-5h |
| 资源详情页 | 高 | 4-6h | 6-8h | 10-14h |
| 实时日志流 | 中 | 4-6h | 2-3h | 6-9h |
| Exec/Shell | 中 | 6-8h | 3-4h | 9-12h |
| CronJob/Job | 中 | 3-4h | 2-3h | 5-7h |
| HPA | 低 | 4-5h | 3-4h | 7-9h |
| StorageClass/PV | 低 | 3-4h | 2-3h | 5-7h |
| RBAC | 低 | 6-8h | 4-6h | 10-14h |
| Network Policy | 低 | 2-3h | 2-3h | 4-6h |
| 资源趋势图 | 低 | 6-8h | 4-5h | 10-13h |

**总计：69-96 小时**

---

## 实施顺序建议

### 第一批（高优先级，立即实施）
1. Events 查看器
2. 资源详情页（Pod、Deployment）

### 第二批（中优先级，1-2 周后）
3. CronJob/Job 管理
4. 实时日志流

### 第三批（中优先级，2-4 周后）
5. Exec/Shell

### 第四批（低优先级，按需实施）
6. HPA
7. StorageClass/PV
8. RBAC
9. Network Policy
10. 资源趋势图

---

## 技术债务

### 需要解决的问题
1. **Django Channels 集成**
   - 实时日志流和 Exec/Shell 需要 WebSocket
   - 需要从 WSGI 迁移到 ASGI（或混合模式）
   - 需要配置 Daphne 或 Uvicorn

2. **前端框架升级**
   - 当前使用 Alpine.js（轻量但功能有限）
   - 复杂交互（如 Web Terminal）可能需要 Vue.js 或 React

3. **数据库迁移**
   - SQLite 不适合生产环境
   - 建议迁移到 PostgreSQL 或 MySQL

4. **缓存优化**
   - LocMemCache 不支持多进程
   - 建议使用 Redis

5. **权限系统完善**
   - 当前权限系统较简单
   - 需要更细粒度的 RBAC

---

## 文档待补充

1. **用户手册**
   - 如何导入集群
   - 如何管理资源
   - 常见问题 FAQ

2. **开发文档**
   - 架构设计
   - API 文档
   - 贡献指南

3. **部署文档**
   - Docker 部署
   - Kubernetes 部署
   - 生产环境配置

---

## 已完成的改进记录

### 2026-04-21：Dashboard 节点卡片补充系统信息

#### 改动内容
1. **后端 `clusters/views.py`** - `_fetch_metrics_data()` 的 `fetch_nodes()` 函数新增从 `node.status.node_info` 提取：
   - `container_runtime` - 容器运行时版本（如 containerd://1.7.x）
   - `os_image` - 操作系统版本（如 Ubuntu 22.04.3 LTS）
   - `kernel_version` - 内核版本
   - `kubelet_version` - Kubelet 版本（即 K8s 版本）
   - `arch` - CPU 架构（如 amd64、arm64）

2. **前端 `templates/dashboard/index.html`**
   - **有 Metrics 的节点卡片**：在 CPU/内存进度条下方新增分隔线 + 2列系统信息网格，用不同颜色图标区分：
     - 容器运行时（cyan）、K8s 版本（blue）、OS（violet）、内核（amber）、架构（emerald）
   - **无 Metrics 的容量表格**：新增 3 列（容器运行时、系统、K8s 版本）

#### 涉及文件
- `clusters/views.py` - `_fetch_metrics_data()` → `fetch_nodes()` 内部函数 + 数据组装部分
- `templates/dashboard/index.html` - 有 Metrics 节点卡片区域 + 无 Metrics 容量表格

---

### 2026-04-22：Dashboard 节点卡片补充角色/状态/GPU + 分页

#### 改动内容
1. **后端 `clusters/views.py`** - `_fetch_metrics_data()` 新增字段：
   - `status` - 节点状态（Ready/NotReady，来自 conditions）
   - `roles` - 节点角色（master/worker/control-plane，来自 labels）
   - `gpu_model` - GPU 型号简称（如 A100，来自 nvidia.com/gpu.product label）

2. **前端 `templates/dashboard/index.html`**
   - 节点卡片头部：左侧加 Ready/NotReady 状态小圆点（绿/红），右侧加 GPU 型号×数量 + 角色 badge
   - 节点卡片区域加分页：每页 20 条，搜索/排序时自动重置到第 1 页
   - 分页控件：首页/上一页/页码/下一页/末页，节点总数显示

#### 涉及文件
- `clusters/views.py` - `_fetch_metrics_data()` → `fetch_nodes()` + 数据组装
- `templates/dashboard/index.html` - 节点卡片头部 + Alpine.js 分页逻辑

---

### 下一步计划
- 继续重构其他资源管理页面（Pods、Deployments 等），统一使用 chart-card 外框 + 分页
- 进入 Phase 2 功能开发（Events 查看器、资源详情页等）

---

### 2026-04-22：节点管理分页 + Pod 日志查看

#### 改动内容
1. **Dashboard `templates/dashboard/index.html`**
   - 节点资源明细区域外层加 `chart-card` 外框（与截图一致）

2. **`templates/clusters/nodes.html`** - 节点列表加分页
   - 每页 20 条，搜索/筛选时自动重置到第 1 页
   - 分页栏：首页/上一页/页码/下一页/末页 + 总条数

3. **`templates/clusters/node_detail.html`** - Pod 列表加分页 + 日志查看
   - Pod 列表每页 20 条，搜索时自动重置
   - Pod 表格新增「日志」按钮，点击弹出全屏日志 Modal
   - 日志 Modal：黑色终端风格，自动滚动到底部，支持刷新

4. **`clusters/views.py`** - 新增 `pod_logs_api()`
   - 获取指定 Pod 的最近 200 行日志
   - 支持 `container` 参数指定容器，默认取第一个容器

5. **`clusters/urls.py`** - 新增路由 `/<pk>/pod/<ns>/<pod>/logs/`

#### 设计规范（后续所有资源页面遵循）
- 所有列表页：外层用 `chart-card` 包裹，内含搜索/筛选 + 表格 + 分页
- 分页：每页 20 条，搜索/筛选时重置到第 1 页
- 状态：统一用小圆点（emerald/amber/rose）+ 文字
- 操作按钮：ghost 风格，hover 时显示颜色

#### 涉及文件
- `clusters/views.py` - 新增 `pod_logs_api()`
- `clusters/urls.py` - 新增日志路由
- `templates/dashboard/index.html` - 节点明细加外框
- `templates/clusters/nodes.html` - 分页
- `templates/clusters/node_detail.html` - Pod 分页 + 日志 Modal

---

**最后更新：2026-04-22**

### 2026-04-22：节点管理页面 UI 重构

#### 改动内容
1. **`templates/clusters/nodes.html`** - 节点列表页
   - 4 个统计卡片换用 `dash-card` 渐变风格（blue/emerald/rose/violet）
   - Ready 和 NotReady 卡片底部加进度条
   - 节点表格：状态列改为小圆点 + 文字，GPU 列拆分为类型 badge + 规格文字，角色列改为 bg-base-200 小 badge
   - 整体容器从 `card bg-base-100` 换为 `chart-card`

2. **`templates/clusters/node_detail.html`** - 节点详情页
   - 顶部 5 个信息卡片换用 `dash-card` 渐变风格（状态/类型/角色/K8s版本/架构）
   - 状态卡片根据 Ready/NotReady 动态切换 emerald/rose 渐变
   - Action Bar 按钮换为带颜色边框的 ghost 风格（amber/rose），停止调度时显示 badge 提示
   - 资源容量 + 系统信息卡片换为 `info-card` + `info-row` 样式
   - Pod 表格：命名空间改为 bg-base-200 小 badge，状态改为小圆点 + 文字
   - 两个确认弹框（Drain/删除）样式统一，使用颜色边框按钮

#### 涉及文件
- `templates/clusters/nodes.html` - 完整重构
- `templates/clusters/node_detail.html` - 完整重构

---

**最后更新：2026-04-22**
