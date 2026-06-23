# Changelog

本文档记录 Armada 项目每日的功能变更、Bug 修复和优化改进。

---

## 2026-06-23

### Bug 修复
- 资源详情弹框 Events 标签看不到真正的失败原因：原先只查 `involvedObject.kind=<控制器>` 的事件，而镜像拉取失败(ErrImagePull/ImagePullBackOff)、CrashLoopBackOff、调度失败(FailedScheduling) 等关键事件 K8s 都挂在 Pod 上，导致 Deployment/StatefulSet/DaemonSet/Service 的 Events 里永远只有 controller 发的 ScalingReplicaSet 这类 Normal 事件。改为聚合「控制器自身 + 其管理的 Pod」的事件（单次拉取 namespace events 后内存过滤，不随 Pod 数放大），并新增「对象」列标识每条事件来源，四种资源统一修复
- Events 消息列原 `truncate` 截断且无 tooltip，长消息（如完整镜像拉取错误）看不全：改为自动换行展示完整内容

---

## 2026-06-22

### 优化改进
- 资源列表操作列图标化：原先 icon+文字按钮（依赖横向滚动）统一改为 28px 紧凑图标按钮，按语义分组（查看 | 操作 | 危险）并用细分隔线分隔，危险/警告操作 hover 用主题色高亮；native title 做 tooltip 避免在 overflow-x-auto 表格中被裁剪。覆盖全部 10 种资源（Deployment/StatefulSet/DaemonSet/Pod/Service/Ingress/PVC/ConfigMap/Secret/Namespace），其中 Namespace 保留 Terminating 强制完成与受保护命名空间的条件渲染
- 仪表盘统计卡视觉降噪：去掉重渐变背景、漂浮光斑和 hover 上浮，改为纯色 base-100 面板 + 左侧细色条标识类别，仅保留极轻的 hover 边框/阴影
- 登录页跟随主题：原 397 行硬编码深色内联样式重写为复用 DaisyUI 语义 token（oklch 变量），并在页面加载时同步读取 localStorage 主题，登录页与主应用明暗一致、不再写死深色

### 新功能
- Service 详情弹框（概览/Endpoints/Events/关联 Pods），展示端口映射、Endpoint 就绪状态、关联 Pod 列表

---

## 2026-05-14

### 新功能
- StatefulSet/DaemonSet 详情弹框增加滚动更新提示横幅（与 Deployment 对齐）

### Bug 修复
- StatefulSet/DaemonSet 回滚版本列表重启后产生重复版本（kubectl.kubernetes.io/restartedAt annotation 带时间戳导致 template 去重失效）
- Deployment 详情弹框关联 Pods 显示了其他资源类型的 Pod（纯 label selector 过滤不够精确，改为 label + ownerReferences 双重过滤）
- 资源列表切换命名空间后页面闪回全部数据再跳回筛选结果（并发 fetch 竞态，用 AbortController 取消旧请求）

### 优化
- 详情弹框警告/提示横幅增强背景色（浅黄色/浅蓝色），暗色主题下文字可读性修复
- 回滚弹框「回滚到此」按钮加 whitespace-nowrap 防止缩小浏览器时换行

---

## 2026-05-13

### 优化
- Deployment/StatefulSet/DaemonSet 详情弹框 + Pod 日志弹框全面改用 DaisyUI 语义化主题类，跟随系统亮/暗主题切换

---

## 2026-05-11

### 新功能
- 仪表盘无 Metrics Server 时通过 Pod requests 汇总显示节点资源分配率
- DaemonSet 新增「重启」按钮，与 Deployment/StatefulSet 对齐

### Bug 修复
- 顶部导航栏切换集群后资源列表仍显示旧集群数据
- 详情弹框关闭后列表副本数未同步更新
- 节点 Drain 后状态误显示为 "Uncordon"
- SQLite "database is locked" 误报为集群连接异常（PRAGMA 配置未生效，改用 connection_created 信号）
- StatefulSet/DaemonSet 回滚版本列表显示扩缩容产生的重复版本（按 pod template 去重）

---

## 2026-05-09

### 新功能
- 添加 Armada 自定义 favicon

### Bug 修复
- StatefulSet/DaemonSet 详情弹框 Pod 列表加载慢（改用 label + ownerReferences 双重过滤）
- 重启/扩缩容后列表页和详情弹框不实时更新

---

## 2026-05-08

### 新功能
- StatefulSet 和 DaemonSet 新增「详情」「回滚」功能
- 详情/回滚弹框通用化，支持 Deployment/StatefulSet/DaemonSet 三种工作负载
- Deployment 详情弹框自动刷新（6 秒间隔）+ 回滚/Events/Pods 分页

### Bug 修复
- 列表页轮询不健康工作负载时未强制刷新后端缓存

---

## 2026-05-07

### 新功能
- Deployment 详情关联 Pods 支持删除异常 Pod（ImagePullBackOff 等）
- Deployment 详情新增滚动更新卡住/进行中提示
- 列表页不健康工作负载自动轮询（5 秒间隔，60 秒后停止）

### Bug 修复
- 所有资源创建时间显示比北京时间慢 8 小时
- SQLite 并发写冲突导致前端误显示"集群连接异常"（启用 WAL 模式）
- immediate sync 被周期 sync 全局锁阻塞（改为 per-type 粒度锁）
- 全局黄色背景上黄色文字不可读

---

## 2026-04-30

### 新功能
- Deployment 详情弹框（概览/Events/关联 Pods）+ 回滚功能
- 通用 YAML server-side dry-run 校验，错误翻译为中文
- Pod 状态列显示容器级卡点原因（ImagePullBackOff、CrashLoopBackOff 等）
- Deployment 详情健康总览横幅 + 异常 conditions 染红
- README 新增功能截图章节

### Bug 修复
- 回滚/编辑 Deployment 后产生多余 ReplicaSet（剥掉 pod-template-hash 标签）

---

## 2026-04-28

### 优化
- YAML 编辑器更新资源后列表立即反映新值，不再等 cache 同步

---

## 2026-04-27

### 新功能
- 所有 K8s 资源类型支持「+ 新建」按钮（含默认 YAML 模板）
- Namespace 卡 Terminating 时新增「强制完成」应急按钮
- YAML 弹窗默认只读预览，需手动切换编辑；Pod YAML 强制只读
- YAML GET 剥掉运行时字段（对齐 kubectl edit）
- NS 删除弹窗增加级联删除警告
- NS 下拉改为可搜索 combobox，仅显示有当前资源类型实例的 NS
- 集群连接状态差异化前端提示（后端挂了/集群连不上/同步中/真没数据）
- 搜索框支持回车快捷刷新
- 禁用账户登录明确提示 + 密码框显示/隐藏切换 + CSRF 失败友好处理

### Bug 修复
- 删除/扩缩容/重启弹框间歇性点击无反应
- Alpine.js 表达式不支持 try/catch 导致弹框监听器全部失效
- YAML 编辑器改 metadata.name 后新建项不显示
- 创建操作 3 秒卡顿无反馈 + 创建后看不到新资源
- apply YAML 时 resourceVersion 残留导致创建失败
- 删除 Namespace 后其他资源列表仍显示该 NS 下的资源
- 改 Deployment YAML 保存后列表仍显示旧值
- 回滚后端口越滚越多（strategic merge patch → replace）
- NS 强制完成返回 500
- YAML 验证只做 parse 不做 K8s schema 检查
- Django 模板多行注释被渲染为正文
- 后端服务挂了时前端全空白无提示

### 优化
- 写操作后端异步化 + 前端乐观更新机制（_pendingOps）
- 删除后 Terminating 状态轮询加速
- 登录失败保留用户名 + 自动聚焦密码框
- 删除确认简化（只有集群删除需要输入名称）

---

## 2026-04-25

### 新功能
- Pod 删除新增「强制删除」选项（可选，默认关闭）

---

## 2026-04-24

### 新功能
- 资源列表自动刷新 + 静默刷新 + 页面状态保持（URL query）
- 删除资源显示真实 Terminating 状态，废弃前端墓碑机制

### Bug 修复
- 新增集群后资源永远不显示（sync 线程未自动启动）
- 权限新增表单完全不可用（字段不对齐）
- 权限系统多处漏拦（仪表盘/集群详情/Pod 日志等路径未校验）
- 用户管理编辑/删除按钮无响应

---

## [1.0.0] - 2026-04-24

### 首次发布
- **多集群管理**：通过 kubeconfig 导入集群，查看详情、节点信息
- **全资源 CRUD**：Deployments、StatefulSets、DaemonSets、Pods、Services、Ingresses、ConfigMaps、Secrets、PVCs、Namespaces
- **资源操作**：YAML 编辑、扩缩容、重启、删除、Pod 日志、Pod 终端、节点 Cordon/Drain
- **用户与权限**：Session 认证 + 按集群/模块/操作的三维 RBAC
- **仪表盘与监控**：可选接入 Prometheus 展示 CPU/内存/GPU 指标
- **安全与性能**：Kubeconfig Fernet 加密、后台 60 秒同步缓存、AJAX 动态加载

### 技术栈
Django 6.0 + K8s Python Client + Alpine.js + Tailwind CSS 4 + DaisyUI 5 + SQLite
