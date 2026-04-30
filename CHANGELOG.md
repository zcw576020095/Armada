# Changelog

本文档记录 Armada 项目所有重要的功能变更和 Bug 修复。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增
- **Deployment 详情 & 回滚**（deployment 列表新增「详情」「回滚」按钮）：
  - 后端新增 `GET /resources/<pk>/api/deployments/<ns>/<name>/describe/`、`GET .../revisions/`、`POST .../rollback/` 三个 API
  - `describe_deployment`：一次返回基础信息 / replicas 统计 / conditions / events / 关联 pods（按 selector matchLabels 反查），给 describe modal 用
  - `list_deployment_revisions`：列出 owner 是该 deployment 的 ReplicaSet 历史，按 `deployment.kubernetes.io/revision` 注解倒序；全量拉 RS 用 ownerReferences 过滤（比 label selector 稳）
  - `rollback_deployment`：拿目标 RS 的 `spec.template` 整体 **replace**（不是 patch）回当前 deployment。重要原因：K8s strategic merge patch 对 `containers[].ports/env` 这种 list 按 merge key 合并，只能加不能删 → 回滚后端口越积越多；用 replace 等价 kubectl replace，无 merge 语义
  - 前端：describe modal 三段 tab（概览 / Events / 关联 Pods）；rollback modal 列出历史、支持"回滚到此"（内联黄色确认条，不弹浏览器原生 confirm）；关联 pods 行复用共享 logModal 查日志
- **通用 YAML server-side dry-run 校验**（所有资源类型共用）：
  - 后端 `POST /resources/<pk>/validate/` + `K8sResourceManager.validate_yaml()`：多文档 YAML 逐个走 `create/replace` 的 `dry_run='All'`，让 K8s 自己做 schema / admission / webhook / 配额检查
  - 错误翻译成中文：422 字段不可变 / 必填值 / 非法值 / 409 冲突 / 403 权限 / 404 引用缺失 / 400 unknown field 等都有"💡 小白解释"
  - 警告显式列出"用户写了但会被服务端忽略"的字段（`status` / `metadata.resourceVersion` 等）
  - 前端"验证语法"按钮改调后端 dry-run，错误用 `pre-wrap` 多行展示（带 kind/name + K8s 原始 cause + 中文解释）；Tab 缩进等纯客户端检查保留兜底
- **集群连接状态差异化前端提示**（覆盖所有资源列表）：
  - 后端 sync_service 加 `_sync_last_error` / `get_sync_error`：周期 sync 和 immediate sync 都记录失败原因并翻译（kubeconfig 错 / DNS 解析失败 / 401 凭证失效 / 403 / 超时 / TLS 错…）
  - 列表 API 响应带 `cluster_error` / `syncing` / `never_synced` 三个字段
  - 前端按四类差异化展示：**后端服务挂了**红色 alert / **K8s 集群连不上**黄色横幅 + 中文原因 / **首次同步中**spinner + 自动 3s 轮询 / **真没数据**仅"暂无数据"，不再"所有资源都不显示"一片空白让人猜
- **Deployment 列表引入按钮整合**：除原有 YAML / 扩缩 / 重启 / 删除，新增"详情" + "回滚"两个按钮

### 改进
- **YAML 弹窗默认只读预览 + 按"编辑模式"切换**：有编辑权限的资源（deployment / namespace / configmap / ...）默认进弹窗是只读预览，用户点右上角"编辑模式"开关才进入编辑态；应用/验证按钮也跟着显隐、顶部提示条在 edit / create / readonly 三种模式切换文案
  - Pod / 由 controller 管理的资源（pod_list.html 的 YAML 按钮、deployment 详情里关联 pod 的 YAML 按钮）强制只读，开关隐藏
  - 创建模式（"+ 新建"）保持默认编辑，按钮文案"创建"，紫色模板提示
- **YAML GET 时剥掉运行时字段**（对齐 kubectl edit）：`get_resource_yaml` 在返回给前端前剥掉 `status`、`metadata.resourceVersion/uid/creationTimestamp/managedFields` 以及 `kubectl.kubernetes.io/last-applied-configuration` 大注解。避免用户看到 status 又改不了、metadata 杂字段干扰
- **Pod 列表默认 YAML 按钮只读**（canEdit=false）：Pod 由 ReplicaSet/StatefulSet/DaemonSet/Job 管理，K8s 不允许直接改大部分 spec 字段；改为只读配一条灰色提示"请改上层资源的 template 触发滚动更新"
- **Namespace 删除弹窗的级联删除警告**（保留醒目橙色警告条，不加 type-to-confirm 输入框）：明确列出会被 K8s 级联清理的资源类型 Deployments / StatefulSets / Pods / Services / ConfigMaps / Secrets / PVCs / Jobs 等；**只有 cluster 删除才需要输入名称二次确认，资源类删除一律不要**
- **资源列表命名空间下拉改为可搜索 combobox**（所有资源列表共享）：原生 `<select>` 只按首字母跳转，用户搜 `zcw` 找不到 `test-zcw`。改为 input + 下拉 panel 的自定义控件，支持**子串模糊匹配**；点击 panel 外自动收起；当前选中有对勾高亮；搜不到时显示"没有匹配 xxx 的命名空间"
- **命名空间下拉仅展示"当前资源类型有实例"的 ns**（各资源类型独立）：deployment 列表下拉只列出至少有 1 个 deployment 的 ns；service 列表只列出有 service 的 ns；避免用户选了之后列表空白
  - 用户当前已选的 ns 即使暂时没数据也保留在下拉里，防止 select 显示空白
  - 排除 Terminating 状态的 ns（从用户视角 ns 已不存在）
- **Deployment describe modal 关联 Pods 表格补齐 Age / 创建时间列**：之前漏展示，后端本就返回 `age` 和 `created` 字段

### 修复
- **删除 namespace 后，其他资源列表仍显示该 ns 下的资源**（所有资源类型通病）：
  - 根因：namespace 删除是异步的（K8s namespace controller 要几秒~几十秒清理内部资源），期间 K8s API 继续返回 deployment/pod → sync cache 也继续有 → 前端看到"删了 ns 但 deployment 还在"
  - 修法 1：`_workload_list_api` 读路径构造"Terminating ns 集合"，把属于这些 ns 的资源从返回结果中过滤掉；ns 下拉也排除 Terminating 的 ns
  - 修法 2：`namespace_delete` / `namespace_force_finalize` 新增 `_purge_namespace_from_cache`：删除后立即把 cache 里 `namespace=删掉的ns` 的条目剔除，防止 sync 拉回老数据；同时级联触发内部资源 cache 刷新
  - 覆盖：deployment / statefulset / daemonset / pod / service / ingress / configmap / secret / pvc
- **改 Deployment YAML 保存后列表仍显示旧值**（致命）：
  - 根因：apply_yaml 触发的是**异步** sync，HTTP 返回时 cache 没刷新；前端 1.5s 后 silent load 拿的是旧 cache → 把 markUpdated 写入的新 replicas/image 覆盖回去
  - 修法：`resource_yaml_api` POST / `deployment_scale` / `namespace_create` / `resource_apply_api` / `resource_delete_api` / `statefulset_scale/restart` / `deployment_restart/rollback` 全部改为 `wait=True`，阻塞等 cache 同步完成再返回
  - 前端 `markUpdated` 改用独立 `update` op（TTL 8s），`_mergePendingOps` 在窗口内强制用 op.resource 覆盖 items 里同 key 项；修复"add op 在 items 里找到同 key 就清掉 op"导致新值被旧 cache 覆盖的 bug
- **Deployment YAML rollback 后端口越滚越多**（致命）：
  - 根因：旧实现用 `patch_namespaced_deployment` + strategic merge patch，K8s 对 `containers[].ports` 按 `containerPort` 做 merge-by-key，**只能加不能删**。回滚到只有 80 端口的旧版本时 K8s 把 80 跟当前 [80, 5000, 2000] 合并还是 [80, 5000, 2000]
  - 修法：改用 `replace_namespaced_deployment`（PUT 整对象），`spec.template` 整体替换，没有 merge 语义，等价 kubectl replace
- **YAML 弹窗底部按钮文案残留"创建"**：先点过"+ 新建"后再点某资源的 YAML 按钮，按钮残留"创建"文案。`openYaml` 每次进入强制重置为"应用到集群"
- **Namespace 强制完成（force-finalize）返回 500**：`read_namespace` 碰到 404（K8s 已清理完成）被通用 except 兜住返回 500。改为 404 时当作"已成功"：清 cache + wait=True 同步 + 返回 success 信息
- **所有资源类型下拉筛选不到刚新建的空 ns**（回退的需求方向：本轮改回"只显示有实例的 ns"）——见上方"改进"条目
- **`'str' object has no attribute 'get'` 致命 bug**：
  - 触发：用户 YAML 里写 `name:test-zcw11`（冒号后缺空格），YAML 解析器把 metadata 整块解析成字符串 `"name:test-zcw11"`
  - 根因：`_validate_one_doc` / `apply_yaml` / `_strip_server_managed_fields` / `_scan_user_facing_dropped` 都直接 `metadata.get()`，遇到字符串就 AttributeError，前端看到没意义的 `'str' object has no attribute 'get'`
  - 修法：所有路径显式 `isinstance(meta, dict)` 防御，报"metadata 字段格式错误：解析结果是 str，最常见原因是 'name: xxx' 后冒号缺少空格"
  - 同样防御 spec / 顶层 doc
- **YAML 编辑器"验证语法"只做 YAML parse 不做 K8s schema 检查**（之前点检查总是通过）：改为调新增的 server-side dry-run endpoint
- **前端多行 `{# #}` 注释被当作正文渲染出来**（Django 模板注释限制）：`{# ... #}` 只支持单行，多行必须 `{% comment %}`。修复 base_list.html 的 ns combobox 说明、pod_list.html 两处多行注释
- **Django 后端服务挂了时前端全空白、无法辨别**：fetch 异常时前端不再 "暂无数据"，改为 alert "后端服务暂不可达" + 重试按钮
- **资源列表无数据时空态文案混在一起**：拆分四种情况（搜索无结果 / 同步中 / 集群连不上 / 真无数据），每种对应专属图标 + 文案 + 操作

### 新增
- **所有 K8s 资源类型支持「+ 新建」**：原本只有 Namespace 有创建按钮，现在 Deployment / StatefulSet / DaemonSet / Pod / Service / Ingress / ConfigMap / Secret / PVC 全部支持
  - 后端：新增 `POST /resources/<pk>/apply/` 通用 API，从 YAML 内容自身解析 `kind/name/namespace`，复用 `apply_yaml`（已支持 create/replace/改名场景）
  - 前端：每种资源给一份**默认 YAML 模板**（包含必填字段示例），点"+ 新建"按钮 → 弹 Monaco YAML 编辑器，用户改完点"创建"即可
  - 复用现有 `yamlModal`（区分 `yamlMode = 'edit' | 'create'`），创建模式下隐藏"编辑模式"开关，按钮文案改为"创建"
  - `apply_yaml` 创建后用 `sync_service._serialize_item` 序列化新资源 → 返回完整 resource 数据 → 前端 `markAdded` 立即可见，与正常列表数据格式一致
  - 权限：复用现有 `can_edit`，无 edit 权限的用户点"+ 新建"会弹"权限不足"提示
- **禁用账户登录明确提示**：密码正确但账户已被禁用时，登录页将显示「该账户已被禁用，请联系管理员」，不再与"密码错误"混淆（其他失败情况仍保持模糊提示以防用户名探测）
- **密码框显示/隐藏切换**：登录页密码输入框右侧新增小眼睛图标，可切换密码明文/密文显示
- **CSRF 失败友好处理**：CSRF 校验失败时自动清理 session 并跳回登录页提示"会话已过期，请重新登录"，不再露出 Django 默认 403 错误页（`CSRF_FAILURE_VIEW = 'accounts.views.csrf_failure_view'`）
- **资源列表搜索框回车快捷键 = 静默刷新**：聚焦搜索框后按 Enter 触发 `load({silent: true})`，从后端拉最新数据校验；搜索关键字、分页、命名空间过滤全部保留；阻止默认行为防止冒泡到外层 form。Placeholder 改为"搜索名称（回车刷新）"提示该功能

### 改进
- 登录失败时 **保留用户名输入**，不再清空表单（此前每次失败用户都要重新输入用户名）
- 登录失败重填时自动聚焦到**密码框**，省一次 Tab
- 简化通用删除确认弹框：除集群删除外，其他所有删除操作（用户、权限、K8s 资源）不再要求输入资源名称二次确认，仅展示资源信息 + 确认/取消按钮；**集群删除仍保留输入名称确认**（高危操作需双重保障）
- 将 `_is_admin` 工具函数抽到 `accounts.models.is_admin_user`，供 views 与中间件共用
- **全站集群下拉与集群列表按权限过滤**：普通用户不再看到自己未被授权的集群，避免点进去才被拒的糟糕体验（管理员不受影响，仍可见全部集群）

### 修复
- **用户管理 - 编辑按钮无响应**：`openEditUser` 使用了 Alpine.js v2 的私有属性 `__x.$data`，但项目实际使用的是 Alpine v3（该属性已移除），导致点击编辑按钮静默抛 `TypeError`。改为 v3 公开 API `Alpine.$data(el)`
- **用户管理 / 权限管理 - 删除按钮无响应、不弹框**：`{% include "components/resource_modals.html" %}` 位置错误地放在 `{% extends %}` 之后、`{% block content %}` 之外。Django 模板继承规则下 block 外的内容会被完全忽略，导致删除弹框 DOM 根本没被渲染，事件派发后无人监听。修复为将 include 移到 `{% block content %}` 内部
- **应用 YAML 后报错"resourceVersion should not be set on objects to be created"（致命）**：
  - 触发场景：在 YAML 编辑器修改 `metadata.name`（K8s 中 name 不可变，相当于创建新对象），原对象的 `resourceVersion` / `uid` / `creationTimestamp` 等服务端字段仍残留在 YAML 里，K8s 拒绝创建
  - 根因：`apply_yaml` 没有在 create 前清理服务端管理字段
  - 修复：新增 `_strip_server_managed_fields(doc)`，在 apply 前移除 `resourceVersion` / `uid` / `creationTimestamp` / `generation` / `managedFields` / `selfLink` / `deletionTimestamp` / `deletionGracePeriodSeconds` / `ownerReferences` 以及整个 `status` 块。replace 时再单独注入 `resourceVersion` 用作乐观锁
  - 效果：改 name、新建资源、原地更新都能正常工作

### 改进
- **写操作后列表更新延迟 + 乐观更新被 load 覆盖（致命体验问题）**：
  - 用户反馈："点创建后按钮卡好几秒，最后页面还看不到新建的 namespace"
  - 根因 1：先前的 `wait=True` 改动让 HTTP 请求阻塞等待 sync 完成（最长 5s），这是按钮卡死的来源；当后台定时同步占用了 cluster lock，等待时间被放大
  - 根因 2：前端乐观插入新 ns 后，1.5s 后 `load()` 拿到的是后端**老 cache**（trigger_immediate_sync 异步还没完成），并且 load 直接 `this.rows = items` 全量覆盖，**乐观插入项被冲掉了**
  - 修复：
    - 后端取消所有写操作的 `wait=True`（恢复异步），HTTP 立刻返回（毫秒级）
    - 前端引入"乐观操作存档"机制 `_pendingOps`：每次 `markAdded` / `markRemoved` / `markTerminating` 都同时登记一条 op（30s TTL）
    - `load()` 拿到后端数据后，在赋值给 `rows` 之前先经过 `_mergePendingOps`：
      - `remove` op：从后端 items 中过滤掉同 key 项；后端已不返回则清理 op
      - `terminate` op：把后端同 key 项强制覆盖为 Terminating；后端已返回 Terminating 则清理 op
      - `add` op：后端缺这个项时合并回来；后端已包含则清理 op
  - 效果：HTTP 响应立即（不卡）、用户操作立即可见（乐观插入不被覆盖）、最终状态正确（后端真同步好后 op 自动退出）
- **加快删除资源后的轮询频率**：检测到 Terminating 资源时，前 30 秒以 2.5 秒间隔轮询（密集观察 K8s 清理进度），30 秒后转 6 秒间隔降低 API 负载，最长持续 120 秒。原 5 秒固定间隔在 K8s 实际清理完成后还要再等 5 秒才能感知到资源消失，体感拖沓
- **YAML 编辑器更新资源后列表显示老 cache 数据**（用户场景：把 deployment 的 replicas 改成 2，列表/扩缩容弹框还显示 1）：
  - 根因：`apply_yaml` 的 update 路径只触发了异步 `trigger_immediate_sync`，1.5s 后 silent load 拿的是 cache，cache 还没追上 K8s 最新值 → 列表/弹框显示老数据
  - 后端：`apply_yaml` 的 update 路径保存 `replace_method` 返回的最新对象，用 `_serialize_item` 序列化后放进 `actions[].resource`
  - 前端：`base_list.markUpdated(resource)` 直接用最新数据替换 `rows` 里的对应项（不依赖 cache 同步窗口）；`applyYaml` 收到 `updated + resource` 派发 `{action:'update', resource}`，`base_list` 事件分发器据此调 `markUpdated`
  - 效果：YAML 改完后列表立即显示新值（replicas / image / 任何字段），扩缩容弹框打开也是最新值
- **删除/扩缩容/重启等弹框间歇性"点击没反应"**：
  - 触发场景：上一次操作中途出问题（网络错误、ESC 关闭、用户切换标签等）导致 `<dialog>` 的 open 状态没正确同步；下次再点击删除按钮时 `dialog.showModal()` 因 dialog 已是 open 状态而抛 `InvalidStateError` → 事件处理器静默失败 → 用户感觉"按钮没反应"
  - 修复：所有 `@open-xxx-modal.window` 监听器在 `showModal()` 前先 `if (modal.open) modal.close()`（已关闭时 close 是 no-op）
  - 覆盖：`deleteModal` / `scaleModal` / `restartModal` / `forceFinalizeModal`
- **Alpine.js 表达式不支持 try/catch 导致弹框监听器全部哑火（致命）**：
  - 现象：控制台报 `Alpine Expression Error: Unexpected token 'try'` + `Uncaught SyntaxError: Unexpected token 'try' at new AsyncFunction`，所有删除/扩缩容/重启按钮点击无反应
  - 根因：Alpine v3 用 `new AsyncFunction(...args, expression)` 编译指令表达式，并把 expression 当成"返回值表达式"包装。`try {} catch {}` 是 statement 不是 expression，因此整个监听器编译失败、不会绑定到事件
  - 修复：去掉所有 `@open-xxx-modal.window` 内联表达式里的 try/catch；普通 `<script>` 标签内的 JS 函数（如 `validateYaml`）保留 try/catch（合法 JS 函数体）
  - 同时去掉了内联表达式里的 `//` 注释 —— 在某些 Alpine 编译路径下多行 `//` 可能吞掉后续代码
- **搜索框「✕ 清空」按钮定位错乱，浮在搜索框下方**：
  - 第一版用 `top-1/2 -translate-y-1/2`，在 flex 父容器嵌套场景下 `.relative` 高度计算异常
  - 第二版改 `inset-y-0 my-auto inline-block`，但 Tailwind CSS 4 是预编译模式（README 里的 `npx @tailwindcss/cli ... --watch`）：开发者若没在跑 watch，新加的 class 不在 `output.css` 里，浏览器无法识别，按钮失去定位样式 → 退化为普通 block 元素显示在 input 下方
  - 最终：改用**内联 `style`** 直接写 `position:absolute + right + top:50% + transform: translateY(-50%)`，不依赖 Tailwind 编译，CSS reset / 编译流程都不会再影响
- **YAML 编辑器修改 metadata.name 后新建项不显示**（解决"改 name 后必须刷新页面才看到新建项"）：
  - 触发场景：在 YAML 编辑器把 namespace 的 `metadata.name` 改成新名字 → K8s 视为创建新资源（name 不可变）→ 走 apply_yaml 的 create 分支。但 yaml 编辑器以前没区分"创建"还是"更新"，前端只派发空的 resource-updated 事件，列表 silent load 拿到的还是后端老 cache → 新建项不可见，必须 F5
  - 后端 `apply_yaml` 增加返回值 `actions: [{kind, name, namespace, action: 'created'|'updated', resource?}]`，namespace 类型的 created action 同时返回简化的 resource 数据（name/status/age/created）
  - 前端 `applyYaml`：根据 `actions` 区分派发事件
    - `created` + 带 resource：派发 `{action:'create', resource}` 触发 base_list.markAdded 立即插入
    - `updated`：派发空事件让列表 silent load 拉最新数据
  - YAML 弹窗关闭延迟从 1500ms 缩短到 600ms（更顺畅）
- **新建资源时的体验优化**（解决"点确认 3 秒后才退出 + 新建项搜不到"）：
  - 创建按钮在请求中显示 spinner 图标 + "创建中..." 文案 —— K8s API 本身需要 1-3 秒（admission webhook、etcd 同步等），给出明确的等待反馈避免误以为卡死
  - `markAdded` 检测到新建项不匹配当前搜索条件时**自动清空搜索 + toast 提示**，避免"创建成功但被搜索过滤掉看不见"
  - 创建后自动跳回第一页确保新建项可见
  - 搜索结果为空时区分文案：`暂无数据`（真没数据）vs `没有匹配 "xxx" 的结果`（搜索过滤掉了），并提供"清空搜索"快捷按钮
  - 搜索框右侧加 ✕ 清除按钮，方便快速清空
- **Namespace 卡 Terminating 时新增「强制完成」应急按钮**：
  - 场景：namespace 长时间停在 Terminating 状态（常见原因：集群里某个 APIService 不可用、namespace controller 卡死、finalizer hook 不响应），观感上像"删不掉"
  - 触发条件：仅 Terminating 状态的 namespace 行才显示「⚡ 强制完成」按钮（与正常的删除按钮互斥）
  - 实现：调 `PUT /api/v1/namespaces/{name}/finalize` 清空 `spec.finalizers`，K8s 立即从 etcd 删除该 namespace
  - 弹窗有明显警告：操作不可逆、可能产生孤儿资源、应先排查集群侧问题
  - 提供给用户对应的诊断思路：先 `kubectl get apiservices` 找 `Available=False` 的服务
- 注：Namespace 删除后 Terminating 持续 5-30 秒是 K8s 本身行为（清理内部 Pod / Service / Secret / ConfigMap / ServiceAccount 的 finalizer 链），与 kubectl delete ns 完全一致；Armada 不提供"强制删除 Namespace"选项以避免遗留孤儿资源

### 改进（基础设施）
- **抽出 `accounts.models.is_admin_user(user)` 工具函数**，供 views / 中间件共用，替代各处重复的内联 `_is_admin` 实现
- **修复 K8s Client Pool 的临时 kubeconfig 文件泄漏**：原实现 `tempfile.NamedTemporaryFile(delete=False)` 写完即遗留在 `/tmp/`（**含明文 kubeconfig，安全隐患**）。改为加载完毕后在 `finally` 立即 `os.unlink`
- **修复 K8s Client Pool 的并发竞态**：多线程同时拉取同一集群 client 时可能重复加载，加 `_load_lock` + double-check 模式确保只加载一次
- **新增 `clusters/pod_logs.py`**：抽出共享的 Pod 日志获取逻辑，给 clusters / resources 两个视图复用
- **新增 `templates/components/toast.html`**：全站 toast 提示组件，由 `base.html` 统一 include，所有页面 `showToast(msg, type)` 即可调用

### 新增
- **Pod 强制删除选项（可选，默认关闭）**：
  - 删除 Pod 的确认框里新增「强制删除」复选框（仅 Pod 类型展示），勾选后传 `grace_period_seconds=0` + `propagation_policy=Background`，跳过 30 秒优雅退出期立即清除
  - 默认不勾，保留 K8s 标准 30 秒优雅期（显示 Terminating 状态）—— 保护 StatefulSet / 带 PV / 有状态服务的数据安全
  - 前端乐观更新：勾选强制删除时直接从列表移除（立即消失），未勾选时显示 Terminating 状态
  - 确认按钮文案跟随勾选状态动态切换：`确认删除` ↔ `强制删除`
- **资源列表自动刷新与状态保持**：
  - 删除操作后除 1.5s 首轮 silent load 外，检测到 `Terminating` 资源时**每 5s 自动后台轮询**直到资源消失（最长 90s），无需手动 F5 —— 从点击删除到 Pod 彻底消失全程无人工干预
  - 页面状态（命名空间筛选、搜索关键字、当前页码）写入 URL query，**刷新页面或分享链接时保持原位置**，不再跳回全量第 1 页
  - 新增 `silent` 模式：自动刷新不闪骨架屏，右上角显示淡出的"🔄 刷新中"指示器；仅首次加载才展示骨架屏
  - 分页越界保护：资源减少后当前页超出范围时自动回退到最后一页
- **删除资源的状态反馈重做：显示真实 Terminating 状态，废弃墓碑机制**：
  - 原先的前端墓碑方案是"视觉欺骗"：删除后直接隐藏，但刷新页面/列表同步重新拉取后资源又出现，用户质疑"我到底删成功没？"
  - 改为与 kubectl 一致的行为：**后端同步时检测 `metadata.deletion_timestamp`**，若有则将 `status_phase` / `status` 标记为 `Terminating`；前端据此展示橙色徽章 + 旋转 spinner 图标
  - Pod / Namespace（有 K8s 优雅退出期）：删除后**乐观改状态为 Terminating**，1.5s 后后端真实数据覆盖；刷新页面也能正确显示 Terminating（不再消失又出现）；若删除卡住（finalizer 等原因），用户能一直看到 Terminating 知道"有问题"
  - Deployment / Service / ConfigMap / Secret / PVC / Ingress 等无优雅期资源：删除后立即从列表移除（删除弹框事件携带 `type` 让 `base_list` 区分处理）
  - `resourceList` 暴露两个方法：`markTerminating(name, ns)` 改状态 / `markRemoved(name, ns)` 移除
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
