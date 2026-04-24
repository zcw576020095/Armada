# Changelog

本文档记录 Armada 项目所有重要的功能变更和 Bug 修复。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增
- **禁用账户登录明确提示**：密码正确但账户已被禁用时，登录页将显示「该账户已被禁用，请联系管理员」，不再与"密码错误"混淆（其他失败情况仍保持模糊提示以防用户名探测）
- **密码框显示/隐藏切换**：登录页密码输入框右侧新增小眼睛图标，可切换密码明文/密文显示
- **CSRF 失败友好处理**：CSRF 校验失败时自动清理 session 并跳回登录页提示"会话已过期，请重新登录"，不再露出 Django 默认 403 错误页（`CSRF_FAILURE_VIEW = 'accounts.views.csrf_failure_view'`）

### 改进
- 登录失败时 **保留用户名输入**，不再清空表单（此前每次失败用户都要重新输入用户名）
- 登录失败重填时自动聚焦到**密码框**，省一次 Tab
- 简化通用删除确认弹框：除集群删除外，其他所有删除操作（用户、权限、K8s 资源）不再要求输入资源名称二次确认，仅展示资源信息 + 确认/取消按钮；**集群删除仍保留输入名称确认**（高危操作需双重保障）
- 将 `_is_admin` 工具函数抽到 `accounts.models.is_admin_user`，供 views 与中间件共用
- **全站集群下拉与集群列表按权限过滤**：普通用户不再看到自己未被授权的集群，避免点进去才被拒的糟糕体验（管理员不受影响，仍可见全部集群）

### 修复
- **用户管理 - 编辑按钮无响应**：`openEditUser` 使用了 Alpine.js v2 的私有属性 `__x.$data`，但项目实际使用的是 Alpine v3（该属性已移除），导致点击编辑按钮静默抛 `TypeError`。改为 v3 公开 API `Alpine.$data(el)`
- **用户管理 / 权限管理 - 删除按钮无响应、不弹框**：`{% include "components/resource_modals.html" %}` 位置错误地放在 `{% extends %}` 之后、`{% block content %}` 之外。Django 模板继承规则下 block 外的内容会被完全忽略，导致删除弹框 DOM 根本没被渲染，事件派发后无人监听。修复为将 include 移到 `{% block content %}` 内部
- **删除资源后列表短暂残留（体验问题）**：后台 `trigger_immediate_sync` 以异步线程方式执行，K8s list + 序列化 + 写 DB 需要 500-1500ms，但前端 `resource-updated` 事件只延迟 500ms 就重新拉取，大概率拿到的还是旧缓存，用户短暂看到"已删除的资源仍在列表里"再过一会才消失。修复：
  - 前端乐观更新：删除成功后立即从 `rows` 数组中移除该项（删除弹框派发事件时携带 `{action: 'delete', name, namespace}` detail）
  - 延迟时间 500ms → 1500ms：给后台同步更充足的完成时间，1.5s 后再次 `load()` 做最终校验
- **新增集群后资源永远不显示（致命）**：`resources/apps.py:ready()` 仅在 Django 启动时一次性扫描 `status='online'` 的集群并启动各自的同步线程，**通过 Web 界面新加的集群永远不会被纳入同步**，必须重启 Django 才能看到资源 —— 这就是用户反馈"导入集群 20 分钟后 Deployment / Namespace 等仍为空"的原因。修复：在 `_refresh_cluster_info` 中检测到集群上线时立即调用 `start_sync_for_cluster`（重复调用安全，内部有 `is_alive()` 判断）。同时 `cluster_delete` 调用 `stop_sync_for_cluster` 清理线程，避免被删除集群的同步线程持续报错
- **添加权限功能完全不可用（致命）**：权限管理页的新增表单存在多处字段不对齐，以及集群字段是文本输入（没法选择集群）
  - `name="user"` vs 后端 `user_id` → 用户 ID 丢失
  - `name="cluster"`（文本输入 + 让用户手打）vs 后端 `cluster_id` → 集群 ID 丢失
  - `name="module"`（单选 select）vs 后端 `modules`（`getlist` 多选）→ 模块全丢
  - 表单直接 `form POST`，但 view 返回 JSON → 成功/失败页面都显示 JSON 原文
  - 修复：集群改为下拉 `<select cluster_id>`、用户字段改为 `user_id`、模块改为多选 checkbox 组（带全选/清空快捷按钮）、表单改为 AJAX 提交 + toast 反馈
- **权限系统多处漏拦（严重安全漏洞）**：原 `PermissionMiddleware` 只覆盖 `/resources/` 与 `/clusters/<pk>/nodes|node` 路径，以下场景全部漏拦，**任何登录用户都可访问**（包括被取消权限的用户）：
  - 根路径 `/`（仪表盘）— 未做 `dashboard` 模块权限校验
  - `/clusters/<pk>/` 详情、`/edit`、`/delete`、`/refresh`、`/prometheus`、`/metrics`、`/debug-prom` — 全部未做 `cluster` 模块校验
  - `/clusters/add/` — 应仅管理员可访问，但普通用户也能添加集群
  - `/clusters/<pk>/pod/<ns>/<name>/logs/` — 未做 `pod` 模块校验
  - 重构中间件后逻辑变为白名单制：**管理员放行 → 个人页/登出放行 → 管理员专属拦截 → Dashboard 按集群级权限校验 → 集群/资源按 `(cluster_id, module)` 校验 → 其他默认放行**

---

## [1.0.0] - 2026-04-24

### 新增 - 首次发布
- **多集群管理**：通过 kubeconfig 添加/导入 Kubernetes 集群，查看集群详情（版本、API Server、节点、状态），编辑显示名称/描述/kubeconfig，后台刷新集群信息
- **全资源 CRUD**：覆盖 K8s 核心资源
  - 工作负载：Deployments、StatefulSets、DaemonSets、Pods
  - 网络：Services、Ingresses
  - 配置：ConfigMaps、Secrets
  - 存储：PersistentVolumeClaims
  - 命名空间：Namespace 管理
- **资源操作**：在线编辑 YAML、一键扩缩容（Deployment / StatefulSet）、重启、删除、Pod 实时日志、Pod 终端直连、节点 Cordon / Uncordon / Drain
- **用户与权限管理**：
  - 基于 Session 的认证 + 管理员/普通用户双角色
  - 按集群、按模块（13 个）、按操作类型（view/edit）的三维细粒度 RBAC
  - 自定义权限校验中间件全局拦截
- **仪表盘与监控**：
  - 可选接入 Prometheus：CPU / 内存使用率图表、节点指标热力图、GPU 节点统计
  - 未接 Prometheus 时降级为节点容量概览与资源分配展示
- **安全与性能**：
  - Kubeconfig 使用 Fernet 加密存储
  - 后台守护线程每 60 秒同步 K8s 资源到本地缓存
  - 本地数据库缓存使资源加载速度较直接调用 K8s API 提升 100 倍以上
  - AJAX 动态加载 + 轻量 HTML 骨架 + JSON API
- **基础设施**：
  - `SECRET_KEY` 与 `KUBECONFIG_ENCRYPTION_KEY` 从环境变量读取
  - 内置 `.env` 自动加载（无需外部依赖）
  - `.env.example` 文件记录所需环境变量
  - `.gitignore` 覆盖 `db.sqlite3` / `venv/` / `node_modules/` / `.env` 等敏感与产物文件

### 技术栈
- **后端**：Django 6.0.4 + Kubernetes Python Client v35.0.0 + Prometheus Client（可选）
- **前端**：Django Templates + Alpine.js v3 + Tailwind CSS 4.2 + DaisyUI 5.5 + FontAwesome
- **加密**：cryptography (Fernet)
- **数据库**：SQLite

### 规划中 (Roadmap)
- 全平台操作审计日志（记录所有用户在平台上的操作：谁、何时、对哪个集群的哪个资源、做了什么）
