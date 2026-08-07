# Changelog

本文档记录 Armada 项目每日的功能变更、Bug 修复和优化改进。

---

## 2026-08-08

### 新增内容

- **补齐 README 功能截图（15 张）**：`docs/screenshots/` 下 15 张全部落地，README 引用逐一核对无裂图。成图 3200×2000（视口 1600×1000 + `device_scale_factor=2`），统一 dark 主题。截图由脚本自动完成并自校验：文件字节数、关键元素是否真的在页面上、脱敏是否有残留，任一不过即报失败，避免把白屏或空壳弹窗当成功
  - `yaml-validate.png` 是**故意注入 `replicas: -5`** 让 K8s 真实 dry-run 返 422 截出来的，不是摆拍；`pod-exec.png` 里是真正连上的 shell，跑了 `whoami`/`uname -sr`/`ls /`

- **截图脱敏规则**（记录在 `docs/screenshots/README.md`，补图请沿用）：该集群 152 个 namespace 里绝大多数是**真人姓名拼音**，且这些名字还会出现在 Pod 名、PFS 路径 `/mnt/pfs/users/<name>`、终端提示符里，只替换「namespace 那一列」远远不够。规则：人名 ns 露前一半后一半打星（`zhangchaowu` → `zhangc*****`）、主机 IP 遮蔽后两段（`192.168.144.10` → `192.168.*.*`）、集群名换示例名、私有镜像仓库实例 ID 打星（`ccr-23gxup9u-vpc.cnc.bj...` → `ccr-********-vpc.cnc.bj...`，阿里 ACR 的 `crpi-<实例ID>` 同理）
  - 有意**保留**的：`kube-system`/`argocd`/`monitoring` 等基础组件 ns、`10.0.0.0/8`/`127.0.0.1` 等网段常量与保留地址、`quay.io`/`ghcr.io`/`public.ecr.aws`/`registry.baidubce.com` 等公共仓库域名。这些人人可见，遮了只会让「这是个真集群」「镜像从哪来」的信息失真，反而像界面出了 bug

### Bug 修复（截图脱敏，均为自查发现）

- **裸子串替换把 `argocd` 打成 `argo**`**：ns 列表里既有 `gocd` 又有 `argocd`，逐个 `split().join()` 会误伤后者，截图上看着像界面出了 bug。改为带字母边界的单次正则 `(?<![a-z])name(?![a-z])`（K8s 名字用 `-` `/` `.` 连接，人名两侧必然不是字母），并按名字从长到短排序，保证嵌套的先被长名吃掉（`zhochendongyu` 早于 `chendongyu`）
- **网段常量被一并遮蔽成 `10.0.*.*/8`**：Pod 日志里 ip-masq-agent 会打 `nonMasqueradeCIDRs:["10.0.0.0/8","172.16.0.0/12",...]`，一律打星后看着像日志查看器把内容弄坏了。改为「带 `/前缀` 且后两段为 0」按网络地址保留，另加 `127.0.0.1`/`0.0.0.0`/子网掩码白名单，真实主机地址照常遮蔽
- **只改 DOM 会得到「半脱敏」**：`TreeWalker` 替换文本节点盖不住三个地方 ——
  - 仪表盘 ECharts 把节点名画进 `<canvas>`，而本集群 240 个节点的名字**就是 IP**（`192.168.144.10` 这种）。canvas 里的字既改不到、`document.body.innerText` 也读不到，于是「DOM 全绿」时图表上 IP 其实全裸。改为在 metrics 接口的响应体上就脱敏，DOM 与 canvas 拿同一份数据，天然一致
  - Monaco 的 model 原文不受 DOM 改动影响，一滚动就重新渲染出真名，需单独 `setValue()`
  - 终端里的主机名/路径来自容器本身，DOM 替换管不到。改为固定挑 `kube-system` 下的 Pod 开终端，从源头上避免人名进 xterm
- **终端截图截成了 404 报错页**：上一版从**已脱敏**的表格 DOM 里回读 Pod 名再发 exec，拿到的是打星后的名字（`aoyu****-motion324-...`），请求必然 404。修复：不再从脱敏后的页面回读标识符，直接指定实测 shell 可用的 Pod，并在截图前断言 `connected` 为真且 xterm 已渲染出内容（实测 443 字符），杜绝再截到报错页
- **泄漏断言差点自己打自己 / 空过**：回读页面查残留时若不放过上述故意保留项，刚留下的 `10.0.0.0/8` 会被判成泄漏；canvas 类内容改为读 ECharts 实例的 option 原始数据，并规定**找到 0 个实例算失败** —— 否则图表没加载完时这条断言是空过的（第一次跑就遇到 0 个实例却仍报「无泄漏」）。另写了一组用例交叉验证 JS 版与 Python 版两个脱敏函数对同一批输入输出完全一致（10/10），避免「DOM 打星了、接口没打」这种更难发现的不一致

### 优化

- **Monaco 从 CDN 改为本地 vendor**：`editor.main.js` 有 947KB，实测 30 秒下不完，YAML 弹窗里编辑器**根本没实例化**（此前 `yaml-edit.png` 截到的是空壳）。改为 `static/js/monaco/vs`（裁剪到 yaml 语言 + 基础 worker，约 4MB），本地加载 5ms、编辑器 1 秒内就绪。与 gsap/echarts/xterm 同一约定：前端依赖不赌 CDN 可用性

---

## 2026-08-07

### 新增功能

- **Pod 容器终端（exec）**：Pod 列表操作列新增「终端」按钮，浏览器内直连容器 shell，不用 kubectl。前端用本地 vendor 的 xterm.js 5.5.0 + fit 插件（不引 CDN，与 gsap/echarts 同一约定），进容器时依次尝试 `bash` → `sh`，多容器 Pod 默认取 `spec.containers[0]`
  - **不走 WebSocket 直通**：项目跑在 WSGI 上（没装 channels/daphne），WebSocket 直通要把部署改成 ASGI 全栈。改为服务端持有那条到 K8s 的 exec WebSocket（`kubernetes.stream`，依赖的 websocket-client 已在），浏览器侧用 HTTP 短轮询收发字节 —— 零部署改造，代价是输入到回显有一个轮询周期延迟。单次轮询最多阻塞 0.6s 且一有输出立刻返回，往返完成后立即发起下一次而不用 `setInterval`（定时器会让请求叠在一起）
  - **权限**：四个端点全部是 POST 且挂在 `/resources/<pk>/pods/` 前缀下，因此自动落到 `PermissionMiddleware` 的 pod 模块 + **edit** 权限校验（进了 shell 等价于对该 Pod 完全控制，只有查看权限不该放行）。会话 token 与创建者 `user_id` 绑定，换个用户拿到 token 也用不了。会话有 5 分钟空闲超时和 32 个总数上限，避免泄漏的会话吃掉 K8s 连接
  - 终端弹窗**故意不放 `.modal-backdrop`**：随手点一下就关掉、把没保存的命令和会话一起丢了，代价太大，只能用右上角关闭按钮退出。非 Running 的 Pod 按钮置灰
  - 本地不回显，由容器里的 shell 自己回显（否则每个字符出现两次）；`window.resize` 时 fit 并把新行列数发给容器

### Bug 修复

- **exec 会打断其它线程的普通 K8s 请求**（做终端时发现，属既有连接池设计缺陷）：`kubernetes.stream.stream()` 的实现（`stream/stream.py:32-46`）会把 `api_client.request` 临时替换成 WebSocket 版本、调用结束再还原。而连接池里的 `ApiClient` 是**跨线程共享**的，在那个替换窗口内，后台同步线程发出的 list 请求会被送到 WebSocket 实现上，报 `Handshake status 200 OK`。实测并发下 60 次 list 有 **3 次**因此失败（第一次跑 exec 测试时就在输出里看到后台同步报了 `Failed to sync pod`）。修复：新增 `K8sClientPool.dedicated_core_v1()` 给 exec/attach 这类 WebSocket 调用返回**独立** client，握手完成后立即 `close()`（WebSocket 由 WSClient 自己持有，close 只回收 ApiClient 的线程池，不影响已建立的连接）。修复后同一并发场景 60 次 list 全部成功
- **xterm.js 与 Monaco 的 AMD loader 撞车导致终端组件加载不出来**（自查发现）：`resource_modals.html` 引了 Monaco 的 AMD loader，它定义了全局 `define`/`define.amd`。xterm 是 UMD 包，一旦检测到 `define.amd` 就走匿名 `define()` 注册，与 Monaco 的 loader 冲突，抛 `Can only have one anonymous define call per script file`，`window.Terminal` 永远挂不上（首次浏览器实测直接报「终端组件未加载」）。修复：加载 xterm 前把 `window.define` 暂存并置空，让 UMD 落到浏览器全局分支，加载完立刻还原给 Monaco 用
- **删除弹框「点好几次才有反应」**（用户反馈）：现象是点删除后弹框闪一下就没了，看起来像没响应。根因不在按钮而在 DaisyUI 的 `.modal-backdrop` —— 它是 `<form method="dialog"><button>` 结构，`showModal()` 一执行就铺满整个视口。用户手快的第二次点击（或误双击）落在遮罩上，直接触发 `method="dialog"` 提交把刚打开的弹框关掉了；用户以为没打开，再点一次，于是「点好几次」。修复新增 `static/js/modal-guard.js`：包一层 `HTMLDialogElement.prototype.showModal` 记录打开时刻，用捕获阶段拦 `.modal-backdrop` 上的 click 与 submit，打开后 450ms 内的遮罩操作一律吞掉。全局生效，覆盖 7 个模板里的 21 个 dialog，不用逐个改。关键是不能把正常功能堵死：守卫窗口过后点遮罩必须照常能关，实测 60/150/300/430ms 连点与真实 `dblclick` 全部保持打开，等 600ms/1000ms 点遮罩正常关闭，Esc 与取消按钮不受影响

- **Pod 列表单响应体 168MB 导致同步失败**（用户反馈）：报错 `IncompleteRead(168443513 bytes read)`，界面提示「集群连接异常，列表数据可能不是最新的」。原因是 `list_pod_for_all_namespaces()` 一次性拉全量，某生产集群 Pod 数量下响应体达 168MB，传输中途连接被中断 —— 这不是超时也不是凭据问题，加大 timeout 没有意义。改为走 K8s 原生的 chunked list：`_list_paginated()` 每页 500 条、靠 `continue` token 往下翻（`V1ListMeta._continue`，已确认 SDK 的 `all_params` 接受 `limit`/`_continue`）。token 过期返 410 时重头翻一次，仍失败才抛。另设 50000 条上限并回传 `truncated` 标记，避免异常规模的集群把内存吃穿。实测 16670 个 Pod 全量同步成功、零报错
  - **需要决策的遗留项**：分页把一次大请求换成 34 次小请求，该集群同步耗时约 244s，而同步周期是 60s，会出现周期重叠。可选方向是拉长该集群的同步间隔、或对 Pod 列表按 namespace 拆分并行。此项未改，等确认后再动

- **节点详情页三个操作按钮在亮色主题下几乎看不见**（自查发现，未流出）：上一轮把 Cordon/Uncordon/Drain/移除节点 从硬编码调色板换成 DaisyUI 语义 token 时用了 `btn-outline btn-warning` 一类写法。`--color-warning` 是 `oklch(82% .189 84.429)`，浅黄色当文字压白底，实测 light 主题下**常态**对比度只有 **1.66**（success 1.84 / error 2.7），静止状态基本读不出来。之前的断言只查了 hover（4.31 通过）没查常态，所以这个问题「通过」了验证 —— 断言已补上常态检查
  - 改法按实测数据选：`btn-outline`/`btn-soft`/`btn-dash` 配任何语义色在 light 下常态全部不达标，实心彩色虽达标（5.24/5.48）但三个排一起太吵。最终走站内既有的那套语言（与 `.row-action`、节点列表「管理」按钮一致）：**常态中性、hover 才上语义色**。实测常态 15.62(dark)/16.68(light)、hover 5.24~5.48，dark/light × 常态/hover 四个态全部 ≥ 4.5
  - 横向扫了一遍全站的 `btn-outline` + 语义色组合，发现日志弹窗的「上次日志」按钮（`previous` 为真时挂 `btn-warning btn-outline`）是同一个毛病，light 下常态 1.73，一并改成同样写法（改后 15.08/17.42 常态、5.24 hover）。集群列表的「选择」按钮虽然也是 `btn-outline` 但没配语义色，实测 15.11/17.42，无需改动

- **集群详情页仍是旧样式**（用户反馈）：详情页的 7 张 `info-card` 没挂 MagicBento，hover 无反应，与已改造的其他页面不一致。两个 grid 容器加 `data-vb-bento`、7 张卡补 `vb-bento-card vb-spotlight-card fx-card` 与入场动效。实测 hover 首卡 `--vb-glow-intensity` = 1.00、鼠标移出后全部归 0

### 验证方法修正

- **对比度测量踩的坑**：候选变体是用 JS 在活页面里注入 class 来量的，但 Tailwind v4 只产出 `@source` 扫描到的类 —— 没被任何模板引用的 `btn-soft`/`btn-dash` 在产物里根本不存在，注入后静默退化成实心按钮。第一轮因此得出「btn-soft 达标 5.24」的**错误结论**（三个变体数字完全相同才暴露出来，实际它们都退化成了同一个实心样式）。修正：候选类先写进临时探针模板、`npm run build:css` 重建，选型定下后删除模板再重建；测量同时回传按钮自身的底色与边框（`borderWidth`/`borderStyle`/`borderColor`），退化立刻可见。`btn-soft` 真正生效后的实际值是 light 1.69，与 `btn-outline` 的 1.66 同样不合格
- hover 一律用真实鼠标移过去后再量，不读 CSS 规则推断；常态量之前先把鼠标移到远处，避免上一个按钮的 hover 未退影响读数
- 探针脚本里的 class 串不写死，与模板保持一致，否则改了模板仍在量旧值
- 全量巡检 9 个页面：`nav`/`aside` 的 computed position 全部为 `fixed`（布局回归探针）、无「已布局但不可见」元素、控制台与 pageerror 零报错
- 集群 pk 改为从集群列表动态发现。此前脚本写死 `CLUSTER=7`，而该集群已不存在（返回 404），导致多次探测拿到空数据、断言在空集合上假通过；现在「数量为 0」一律记 FAIL 而不是跳过

### 终端功能的验证

- 浏览器实登录后点开终端，在真实容器里执行 `echo ARMADA_EXEC_OK_$((6*7))`，断言终端里出现算好的 `ARMADA_EXEC_OK_42` —— 只有 shell 真的执行了才会有这个结果，命令被回显不算通过
- resize 精确比对：容器内 `tput cols` = 143，与 xterm 的 `cols` = 143 一致，证明 resize channel 真的送到了容器
- 会话回收从服务端行为判定，不看前端状态：关闭弹窗后用已作废的 token 再打 `exec/io` 端点，返回 404「终端会话不存在或已过期」
- 权限双向验证：只读用户点终端弹出无权限提示，**并且**直接 fetch `exec/open` 接口也返回 403「无权编辑「Pod」模块」—— 前端拦得住不代表接口拦得住，必须分别验
- 非 Running 的 Pod 按钮置灰：从全量缓存的 12688 个非 Running Pod 里取样，用搜索框过滤到页面上确认 `disabled=true`。第一轮这条是在**空集合**上通过的（当前页恰好全是 Running，检查了 0 行），补验后才算数

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

### 视觉层扩展：移植 vue-bits 组件库

新增 `static/css/vue-bits.css` + `static/js/vue-bits.js`，组件取自 [vue-bits](https://github.com/DavidHDev/vue-bits)（`src/content/**`，本地 clone 后按源码逐个移植）。Armada 是 Django 模板 + Alpine、没有 Vue，因此每个组件都从 SFC 拆成「CSS 那一半 + JS 行为那一半」，靠 `data-vb-*` 属性挂载；原版颜色全是硬编码 hex（`#27FF64`/`#060010`/`#333`，按深色底设计），统一换成 DaisyUI 的 `--color-*` token，同一份代码在 light/dark 下都成立。

已移植：`MagicBento`、`SpotlightCard`、`StarBorder`、`ShinyText`、`GradientText`、`DecryptedText`、`GlareHover`、`Magnet`、`ElectricBorder`、`DotGrid`、`LetterGlitch`、`ClickSpark`、`GradualBlur`、`AnimatedContent`/`AnimatedList`、`Counter`。

保留原版算法与数值的几处关键细节：
- **MagicBento 的邻近度**是它区别于普通 `:hover` 卡片的核心：`proximity = radius*0.5`、`fadeDistance = radius*0.75`，距离在两者之间线性插值写入 `--vb-glow-intensity`，于是整片卡片墙有亮度**梯度**而不是只有鼠标下那张亮；另配一个 `position:fixed` 的全局聚光灯跟随鼠标。亮色主题下 `mix-blend-mode` 从 `screen` 换成 `multiply`（screen 在亮底上会把整片洗白）
- **DotGrid 的推开-回弹**原版依赖 GSAP 的 `InertiaPlugin`，那是付费插件、免费包里没有（已 grep 确认 vendor 的 gsap.min.js 内无此插件）。改为自己积分：推开给初速度，每帧按 resistance 做指数衰减，速度衰减到阈值后用 `elastic.out(1, 0.75)` 的等价实现拉回原位
- **GlareHover** 必须先无过渡复位到 `-100%`、强制 reflow、再设 `100%` 才能重复触发（transition 不会因为 class 移除又加上而重放），所以这一个保留了原版的 JS 写法而没改成纯 CSS
- **ShinyText / GradientText** 原版用 motion-v 的 `useAnimationFrame` 逐帧写 `backgroundPosition`，改成纯 CSS keyframes（等价且不占主线程）；GradientText 的首色需在尾部重复一次才能无缝循环，这是原版的关键细节
- **ElectricBorder** 只移植了它的三层发光边框，canvas 分形噪声抖动那部分刻意没做：对一个管理控制台噪音大于收益，且每张卡一条 rAF 循环不划算

刻意规避的坑：
- **不给 Alpine 托管的数字挂 Counter**：那些数字由 `x-text` 持续驱动，Counter 会和 Alpine 抢 `textContent`
- **图表卡不挂 SpotlightCard**：径向光斑透过半透明图表底色会让折线读数变糊，只留入场动效
- 全屏 canvas（ClickSpark / DotGrid / LetterGlitch）在没有活动粒子、鼠标移出、页面切后台时主动停掉 rAF，不空烧 60fps
- 沿用 armada-fx.css 的同一条禁令：本文件无 `@layer`、优先级高于 Tailwind 的 `@layer utilities`，绝不给 `nav`/`aside`/`main` 设 position

### Bug 修复（本轮视觉层引入 / 既有问题）
- **入场动效把仪表盘 12 张卡片永久藏住**（自查发现，未流出）：`[data-vb-reveal]` 初版由 CSS 无条件设 `opacity:0`，等 IntersectionObserver 回调加 `.vb-in` 才显示。但 `IntersectionObserver` 注册在 `display:none` 的元素上只会回调一次 `isIntersecting:false`，之后 Alpine 把 `x-show` 打开时**不再回调**（已单独写最小用例实测：`callsAfterUnhide: 0`）。而仪表盘的汇总卡/图表卡全在 `x-show="!loading && hasMetrics"` 内，意味着数据加载完之后这 12 张卡会永久停在 `opacity:0`。根因是设计方向错了——把「可见」押在 JS 一定会成功回调上。改为反向契约：隐藏态挂在 JS 添加的 `.vb-armed` 上，且只给 `getClientRects().length > 0`（确认已参与布局）的元素上锁，藏在 `x-show` 里的元素交给 MutationObserver 等 Alpine 打开后再补锁。JS 没加载 / IO 没触发 / 元素被藏 —— 一律保持可见，坏掉的方向是「没动画」而不是「没内容」
- **节点列表「管理」按钮 hover 时文字被色块糊掉**（用户反馈）：该按钮同时写了 `hover:btn-primary` 和 `hover:bg-primary/10`，前者把文字设成浅色的 `primary-content`、后者把底色压成 10% 淡色，结果浅字压浅底。改用 `hover:text-primary` 仍不行——实测深色主题下蓝字压蓝底对比度只有 **2.89**。最终改为与项目既有 `.row-action` 一致的中性配色（`hover:bg-base-content/10` + `hover:text-base-content`），实测对比度 **10.22**。验证手段：在页面内用 canvas 逐层合成真实像素后算 WCAG 对比度（`getComputedStyle` 返回的是 `oklch()`/`oklab()`，不能按 RGB 解析——第一版脚本就是这么错的，得出的整屏数字全是垃圾），覆盖 dark/light × 5 处按钮，现全部 ≥ 4.85
- **多行 `{# #}` 注释被当作文本渲染到操作列**（用户反馈）：Django 的 `{# #}` 只支持单行，多行写法会把注释原文输出到页面。改用 `{% comment %}`，并写脚本全量扫描 `templates/` 确认无其他同类问题
- **各页面 hover 效果不统一**（用户反馈）：初版只给仪表盘和集群列表挂了 MagicBento，节点管理页/节点详情页的统计卡完全没挂，hover 无反应。补齐后四个页面共 20 张卡走同一套效果，并写脚本实测断言（hover 首卡 `--vb-glow-intensity` ≈ 1、邻近卡 > 0、鼠标移出后全部归 0），确认是真生效而非只挂上了 class

### 验证
- 全量巡检 14 个页面 + 登录页：`nav`/`aside` 的 computed position 全部仍为 `fixed`（布局回归探针）、控制台与 pageerror 零报错、无「已布局但不可见」的元素
- 选中集群后的仪表盘单独验证：3 个 ECharts canvas 均为 456x340 非零尺寸、汇总数字正常（22.3% / 26.6% / 256 节点 / 163 GPU）、48 张 SpotlightCard 与 40 张节点卡挂载正常
- hover 辉光一致性：集群列表 2 张 / 节点管理 4 张 / 仪表盘 3 张 / 节点详情 5 张，四页行为一致
- 补记：`metrics` 接口在 256 节点集群上冷缓存需 ~40s（TTL 60s），验证脚本须先预热否则会误判为「图表没渲染」；LocMemCache 是进程内的，预热必须打到同一个 runserver 进程

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
