# Armada 前端重构设计文档

## 项目概述
Armada 是一个企业级 Kubernetes 多集群管理平台，本次重构目标是将前端从原有的"花哨、膨胀"风格改造为**商业级、专业、紧凑**的现代控制台风格，参考 Linear、Vercel、Rancher 等优秀产品。

## 设计原则
1. **克制的视觉效果** - 去掉过重的阴影、夸张的 hover 动画、花哨的装饰元素
2. **紧凑的布局** - 减小 padding、缩小字号、收窄间距
3. **有意义的颜色** - 用颜色传达信息（状态、类型、重要性），而非纯装饰
4. **一致的交互** - 统一的按钮尺寸、表格样式、卡片风格
5. **清晰的层次** - 通过字重、透明度、尺寸建立视觉层次，而非依赖边框和阴影

## 已完成的重构

### ✅ 第一阶段：核心布局与登录
1. **登录页面** (`templates/accounts/login.html`)
   - 去掉浮动节点和 SVG 连线动画
   - 改为克制的渐变光晕 + 网格背景
   - 左侧增加产品特性列表
   - 右侧表单更简洁干净

2. **整体布局** (`templates/base.html`)
   - 顶栏从 h-16 缩到 h-14，更紧凑
   - 侧边栏去掉 DaisyUI menu 组件，改用自定义导航项
   - 集群选择器加了过渡动画
   - 侧边栏折叠状态持久化到 localStorage
   - 修复头像字母居中问题（使用 `grid place-items-center` + `mt-px`）

3. **个人设置页面** (`templates/accounts/profile.html`)
   - 改为横向用户信息卡片 + 独立表单卡片
   - 改用 AJAX 提交，保存后显示 toast 提示（不跳转）
   - 更紧凑、更专业

4. **403 页面** (`templates/accounts/forbidden.html`)
   - 统一视觉风格

### ✅ 第二阶段：集群管理
1. **集群列表页** (`templates/clusters/list.html`)
   - 卡片从 `p-6` 收到 `p-5`
   - 去掉 `shadow-lg`、`hover:shadow-2xl`
   - 按钮统一 `h-8 min-h-0 text-xs`
   - Badge 从 `badge-sm` 缩到 `badge-xs`

2. **集群详情页** (`templates/clusters/detail.html`) ⭐ 重点优化
   - **顶部 4 张信息卡片**：各有独立的深色渐变底色（蓝/琥珀/紫/绿），带彩色图标和右上角光晕装饰
   - **节点状态 3 张卡片**：对应颜色（绿/红/紫），带彩色进度条和图标
   - **快速导航 11 个入口**：改为 4 列布局，每个入口独立色调（天蓝/琥珀/翠绿/靛蓝/青/紫/玫红/橙/青绿/黄/粉），hover 时微微上浮 + 阴影
   - 覆盖所有资源类型：节点、命名空间、Deployments、StatefulSets、DaemonSets、Pods、Services、Ingress、ConfigMaps、Secrets、PV/PVC
   - 暗色和亮色主题都做了适配
   - 添加"编辑"按钮

3. **导入集群页** (`templates/clusters/add.html`)
   - 改为 Step 1/Step 2 分步式表单
   - 卡片使用深色渐变底色（蓝/琥珀）
   - 更清晰的视觉层次

4. **集群编辑页** (`templates/clusters/edit.html`) ⭐ 新增功能
   - 新增后端 view：`cluster_edit`
   - 新增 URL：`<int:pk>/edit/`
   - 支持修改：显示名称、描述、Prometheus 地址、Kubeconfig
   - 卡片使用深色渐变底色

5. **节点管理页** (`templates/clusters/nodes.html`)
   - 统计卡片从 `p-6` 收到 `p-4`
   - 表格样式统一

6. **节点详情页** (`templates/clusters/node_detail.html`)
   - 统一视觉风格

### ✅ 第三阶段：仪表盘
**Dashboard 仪表盘** (`templates/dashboard/index.html`) ⭐ 重点优化
- **有 Metrics 时**：
  - 顶部 4 张卡片：CPU 使用率、内存使用率、节点总数、GPU 节点，各有深色渐变底色和彩色进度条
  - CPU & 内存使用率对比柱状图
  - 资源使用热力图
  - 节点资源明细表格（带彩色进度条）
- **无 Metrics 时**：
  - 黄色提示横幅
  - 容量卡片（节点总数、CPU 总容量、内存总容量、GPU 节点）
  - 各节点资源容量柱状图
  - 节点容量明细表格
- 所有卡片都有 hover 动画

### ✅ 第四阶段：资源列表
1. **基础模板** (`templates/resources/base_list.html`)
   - 标题从 `text-lg font-bold` 改为 `text-sm font-semibold opacity-70`
   - 筛选器和搜索框统一 `h-8 min-h-0 text-xs`
   - 表头从 `font-bold` 改为 `font-semibold text-xs`
   - 表格行 hover 从 `hover:bg-primary/5` 改为 `hover:bg-base-200/50`

2. **资源模态框** (`templates/components/resource_modals.html`)
   - YAML 编辑器模态框从 92vw/92vh 缩到 90vw/90vh
   - 按钮统一 `h-8 min-h-0 text-xs`
   - Delete/Scale 模态框统一风格

3. **10 个资源列表页** - 全部统一风格
   - `deployment_list.html` - Deployments
   - `statefulset_list.html` - StatefulSets
   - `daemonset_list.html` - DaemonSets
   - `pod_list.html` - Pods（含日志查看模态框）
   - `service_list.html` - Services
   - `ingress_list.html` - Ingress
   - `configmap_list.html` - ConfigMaps
   - `secret_list.html` - Secrets
   - `pvc_list.html` - PV/PVC
   - `namespace_list.html` - Namespaces（含创建模态框）

### ✅ 第五阶段：用户与权限
1. **用户管理** (`templates/accounts/user_list.html`)
   - 表格统一风格
   - 用户头像改为小圆形渐变
   - 创建/编辑用户模态框

2. **权限管理** (`templates/accounts/permission_list.html`)
   - 表格统一风格
   - 创建权限模态框

## 未完成的功能

### ⏸️ 暂不修改
- **仪表盘图表样式** - 用户表示"这个不能改就先不改了"，保持 ECharts 默认样式

## 技术细节

### 颜色系统
- **状态颜色**：
  - 成功/在线：`green-400` / `green-500`
  - 错误/离线：`red-400` / `red-500`
  - 警告/未知：`yellow-400` / `amber-400`
  - 信息：`blue-400` / `sky-400`

- **资源类型颜色**：
  - 节点：`sky-400`
  - 命名空间：`amber-400`
  - Deployments：`emerald-400`
  - StatefulSets：`indigo-400`
  - DaemonSets：`cyan-400`
  - Pods：`violet-400`
  - Services：`rose-400`
  - Ingress：`orange-400`
  - ConfigMaps：`teal-400`
  - Secrets：`yellow-400`
  - PV/PVC：`pink-400`
  - GPU：`purple-400` / `violet-400`

### 尺寸规范
- **按钮**：`btn-sm h-8 min-h-0 text-xs`
- **输入框**：`input-sm h-9 text-xs` 或 `h-10`
- **Badge**：`badge-xs`
- **卡片 padding**：`p-4` 或 `p-5`（原来是 `p-6`）
- **图标**：`text-xs` (12px) 或 `text-sm` (14px)
- **标题**：`text-sm font-semibold opacity-70`

### 动画效果
- **卡片 hover**：`transform: translateY(-2px)` + `box-shadow: 0 6px 16px rgba(0,0,0,0.2)`
- **过渡时间**：`transition: all 0.15s ease`
- **进度条动画**：`transition-all duration-500`

### 深色渐变卡片
```css
.info-card-blue {
  background: linear-gradient(135deg, #1e2a4a, #172040);
  border-color: rgba(59,130,246,0.15);
}
.info-card-blue::before {
  background: #3b82f6;
  opacity: 0.12;
}
```

## 文件清单

### 已修改的模板文件（共 30 个）
1. `templates/base.html` - 整体布局
2. `templates/accounts/login.html` - 登录页
3. `templates/accounts/profile.html` - 个人设置
4. `templates/accounts/forbidden.html` - 403 页面
5. `templates/accounts/user_list.html` - 用户管理
6. `templates/accounts/permission_list.html` - 权限管理
7. `templates/dashboard/index.html` - 仪表盘
8. `templates/clusters/list.html` - 集群列表
9. `templates/clusters/detail.html` - 集群详情
10. `templates/clusters/add.html` - 导入集群
11. `templates/clusters/edit.html` - 编辑集群（新增）
12. `templates/clusters/nodes.html` - 节点管理
13. `templates/clusters/node_detail.html` - 节点详情
14. `templates/resources/base_list.html` - 资源列表基础模板
15. `templates/components/resource_modals.html` - 资源模态框
16. `templates/resources/deployment_list.html`
17. `templates/resources/statefulset_list.html`
18. `templates/resources/daemonset_list.html`
19. `templates/resources/pod_list.html`
20. `templates/resources/service_list.html`
21. `templates/resources/ingress_list.html`
22. `templates/resources/configmap_list.html`
23. `templates/resources/secret_list.html`
24. `templates/resources/pvc_list.html`
25. `templates/resources/namespace_list.html`

### 已修改的后端文件（共 2 个）
1. `clusters/views.py` - 新增 `cluster_edit` view
2. `clusters/urls.py` - 新增 `/edit/` URL

## 总结

本次重构覆盖了 Armada 前端的所有核心页面，从登录到仪表盘、从集群管理到资源列表、从用户管理到权限控制，全部统一为现代商业级控制台风格。

**核心改进**：
- 视觉更紧凑（padding、字号、间距全面缩小）
- 颜色更有意义（用颜色传达信息，而非装饰）
- 交互更一致（统一的按钮、表格、卡片风格）
- 层次更清晰（通过字重、透明度、尺寸建立层次）
- 新增集群编辑功能

**用户反馈**：
- 登录页："可以非常的满意"
- 集群详情页："可以了很漂亮这次"
- 整体风格："这次好多了"
