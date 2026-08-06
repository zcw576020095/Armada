# Changelog

本文档记录 Armada 项目每日的功能变更、Bug 修复和优化改进。

---

## 2026-08-06

### Bug 修复
- **DaemonSet 回滚历史里「当前版本」永不高亮**：`list_daemonset_revisions()` 从 `ds.spec.template.metadata.labels` 里取 `controller-revision-hash`，但这个 label 是控制器注入到 **Pod** 上的、并不存在于 spec 模板中，导致 `current_hash` 恒为空字符串 → 所有 revision 的 `is_current` 全是 false、`current_revision` 恒为 None，用户在回滚弹框里看不出当前跑的是哪个版本。原代码还用 `hasattr(ds.status, 'current_number_scheduled')` 做守卫，而该字段与 revision 无关，属于无效条件。修复分两处：(1) 新增 `_daemonset_current_revision_hash()`，按 selector 拉取该 DaemonSet 实际拥有的 Pod（label selector 先过滤 + ownerReferences 二次校验，与项目既有 `_list_pods_by_owner` 口径一致），统计 Pod 上 `controller-revision-hash` 出现次数取众数——滚动更新期间新旧 hash 共存，众数即当前主版本；(2) 比较方式也是错的：Pod label 里是**裸 hash**（`6fd988788d`），而 ControllerRevision 的名字是 `<daemonset名>-<hash>`（`cce-gpu-exporter-6fd988788d`），原先的 `cr.metadata.name == current_hash` 恒不成立，改为按 `-<hash>` 后缀匹配。StatefulSet 那边能直接相等比较，是因为 `status.update_revision` 本身就是完整 CR 名，DaemonSet 没有这个字段。对照：Deployment 走 `deployment.kubernetes.io/revision` annotation，本就正确，只有 DaemonSet 缺对应实现。实测 pk=7 集群 6 个 DaemonSet：有 Pod 的 4 个全部正确识别出当前版本且 `is_current` 唯一命中，另 2 个 `desired=0`（无 Pod 调度）返回 None 属预期
- **集群节点指标拉取失败被静默吞掉，前端显示「0 节点」而非报错**：`_fetch_metrics_data()` 的三个并发任务中，`fetch_metrics` / `fetch_pod_requests` 都有 try/except（用量类数据失败降级合理），但硬依赖的 `fetch_nodes` 没有；而 `ThreadPoolExecutor.submit()` 的异常只存在 Future 里，不调用 `.result()` 就永远不会抛出。结果集群不可达/凭据失效时 node_cap 为空字典 → 汇总出全 0 的 summary 正常返回 200，还被 `cached_metrics` 缓存 60 秒，用户看到「0 节点、CPU 0%」会误以为集群真的空了。修复：保留该任务 Future 并显式 `.result()`，让异常抛给已有 `except` 分支转成 `error` 字段展示，同时避免空结果进缓存
- **K8s 原始异常整段渲染到界面，含响应头与 Set-Cookie**：仪表盘/节点页的错误提示直接展示后端的 `str(e)`，而 kubernetes SDK 的 `ApiException.__str__()` 会把完整 HTTP 响应头（含 `Set-Cookie`、`Audit-Id`、`Traceresponse`）和 body 一起拼进字符串，页面上糊出一大段无法阅读的调试信息，同时把 cookie / 审计 ID 暴露到前端。修复：新增 `_friendly_error()`，`ApiException` 只取 `status` + `reason`（401/403 另给「凭证无效或已过期」「权限不足」的中文说明），其余异常复用项目已有的 `_describe_sync_error()` 分类；原始异常改为 `logger.warning` 落日志便于排查。覆盖 `cluster_nodes_api` / `node_detail` / `cluster_metrics_api` 三处
- **仪表盘未选集群时页面大片空白**：原空状态只有一个图标加两行文案居中，视口下方剩一整屏空白，且用户还得先去集群列表页才能切换。改为直接把当前用户可见的集群铺成卡片墙（状态脉冲点 / K8s 版本 / 节点数，点击即进仪表盘），末尾附一张虚线「导入新集群」卡；无任何集群时才回退为引导导入的提示块

### 优化改进
- **新增视觉层 `static/css/armada-fx.css` + `static/js/armada-fx.js`，设计语言移植自 best-resume**（`web/src/style.css` / `web/src/lib/fx.js`）。搬过来的是它那套体系而非单个效果：分层 token（三色光晕 `--fx-a1/a2/a3`、发丝线 `--hair`、三档阴影 `card`/`lift`/`brand`）、两条缓动曲线（`--ease-spring` 回弹用于交互、`--ease-out-soft` 缓出用于展开）、"玻璃 + 发丝边 + 阴影托层次"的容器组合，以及"常驻动效为主、交互动效为辅"的取向。差异点：best-resume 是 Vue + `@theme` + `html.dark`，Armada 是 Django 模板 + DaisyUI v5，因此 token 桥接到 `--color-*` 上、主题跟随 `[data-theme]`
- 常驻动效：三团背景光斑由 GSAP 驱动漂移（各自独立随机时长与目标点，避免 CSS keyframes 那种整组同频摆动的钟摆感）、网格底纹、进度条流光、状态点脉冲、侧栏激活光条、logo 与标题渐变流动
- 交互动效：卡片鼠标跟随柔光、3D 倾斜（限 6° 内，再大就显廉价）、光沿边框游走（`conic-gradient` + `@property` 注册角度，否则只会跳变不补间）、点击水波纹与粒子火花、按钮光泽扫过、表格行左侧指示条
- 本地 vendor 了 `gsap.min.js`（73KB，从 best-resume 的 node_modules 复制），不引 CDN
- 明暗两主题均逐页截图核对；亮色下另调低光晕与网格强度（白底对色偏更敏感）。全部持续动画在 `prefers-reduced-motion: reduce` 下关闭，渐变文字回退纯色
- 刻意没做的：统计数字的计数动效。那些数字由 Alpine 的 `x-text` 驱动，`countUp` 会和 Alpine 抢 `textContent`，属于自找 bug（`armada-fx.js` 里保留了 `countUp`，只对非 Alpine 托管的 `[data-fx-count]` 生效）
- 该文件是**手写 CSS、不参与 Tailwind 编译**，视觉调整无需 `npm run build:css` 重建产物，也不触碰任何 Alpine 状态或 fetch 逻辑；HTML 侧只做加 class 的最小改动
- 登录页同步升级（独立模板不继承 base.html，且自带不透明 body 会盖住全局光晕，故内联一份等效动效）：光晕漂移、网格缓慢平移、品牌图标流光悬浮、标题渐变、特性项依次浮现、按钮光泽扫过，同样带 reduced-motion 降级
- **踩坑记录（CSS 层叠优先级）**：Tailwind v4 的工具类位于 `@layer utilities` 内，而无 `@layer` 的普通样式优先级**高于**任何 `@layer`。最初在 fx 文件里写 `nav, aside, main { position: relative }` 想把内容抬到光晕之上，结果直接压掉了 Tailwind 的 `.fixed`，顶栏与侧边栏丢失固定定位、主内容区塌出整屏空白。正确做法是让背景伪元素用负 `z-index` 自然沉底（并把 `bg-base-200` 从 `body` 移到 `html`、`body` 置透明，否则不透明底色会盖住负层伪元素），完全不碰内容层定位。文件内已留注释警告
- 验证方式：Playwright 实登录后巡检 12 个页面（集群列表/节点/Deployment/Pod/StatefulSet/Service/Namespace/ConfigMap/用户/权限/个人设置/集群详情），逐页断言 `nav` 与 `aside` 的 computed position 仍为 `fixed` 作为布局回归探针，明暗两主题各截图核对，控制台零报错

---

## 2026-07-17

### Bug 修复
- 前端整页丢颜色（白底黑字）：8 个模板的自定义 `<style>` 里有 78 处沿用 DaisyUI v4 的短变量名（`var(--bc)`/`var(--p)`/`var(--b1)` 等），而项目实际是 DaisyUI v5——v5 变量已改名为 `--color-base-content`/`--color-primary`/`--color-base-100`，且变量值本身就是完整的 `oklch(...)`。旧写法 `oklch(var(--bc))` 既引用了不存在的变量、又构成 `oklch(oklch(...))` 双层非法嵌套，导致背景/文字/边框全部失效退回浏览器默认色。统一修复：短名→v5 全名；纯色 `oklch(var(--color-x))`→裸 `var(--color-x)`；带透明度 `oklch(var(--color-x) / .5)`→`color-mix(in oklab, var(--color-x) 50%, transparent)`。涉及 base.html、login.html、dashboard/index.html 及 clusters/ 下 5 个模板
- 新增基于文件 mtime 的缓存破除标签 `static_v`（accounts/templatetags/static_version.py），output.css 的 URL 自动拼 `?v=<mtime>`，重建 CSS 后浏览器强制重新下载，避免样式改了却看到旧缓存。base.html 与 login.html 的 output.css 引用改用 `{% static_v %}`

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
