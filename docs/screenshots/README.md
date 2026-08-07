# 截图目录

存放 README「功能截图」章节引用的图片。GitHub 自动渲染相对路径，无需额外配置。

## 需要的截图（15 张）

主 README 目前引用下面这些文件名，**必须逐字一致**（小写 + 连字符），否则显示成裂图。

| 文件名 | 截什么 | 建议怎么截 |
|---|---|---|
| `dashboard.png` | 仪表盘 | 选中一个接了 Prometheus 的集群，等图表加载完（首次有缓存预热，别截到转圈） |
| `clusters-list.png` | 集群列表 | 至少 2 个集群，能看出多集群切换 |
| `nodes.png` | 节点管理 | 节点列表 + 操作列 |
| `node-detail.png` | 节点详情 | 点进某个节点，含容量/负载与该节点上的 Pod |
| `pod-exec.png` | 容器终端 | 开终端后跑一两条命令（如 `ls`、`hostname`），让画面里有真实输出 |
| `pod-logs.png` | Pod 日志 | 日志弹窗，最好有内容 |
| `pods.png` | Pod 列表 | 如果能找到 `ImagePullBackOff` 之类的行更好，能体现卡点 reason 高亮 |
| `deployments.png` | Deployment 列表 | 含操作列 |
| `deployment-detail.png` | Deployment 详情弹窗 | 概览页，或切到 Events / 关联 Pods 页签 |
| `deployment-rollback.png` | 回滚弹窗 | 能看到多个历史 revision 和「当前版本」标记 |
| `yaml-edit.png` | YAML 在线编辑 | Monaco 编辑器打开某资源 |
| `yaml-validate.png` | YAML dry-run 校验 | **故意写错**一处再点校验，截出中文报错和处置建议 |
| `permissions.png` | 权限管理 | 有几条按集群 × 模块的授权记录 |
| `users.png` | 用户管理 | 用户列表 |
| `login.png` | 登录页 | 直接截登录页 |

## 截图规格

- 视口 **1600×1000**、`device_scale_factor=2`，成图 3200×2000
- 统一 **dark** 主题
- 弹窗类截图连带背景页面一起截（截视口而非弹窗元素），能看出上下文

## 脱敏规则

这些图公开在 GitHub 上，而集群里 152 个 namespace 绝大多数是**真人姓名拼音**，
且这些名字还会出现在 Pod 名、PFS 路径（`/mnt/pfs/users/<name>`）、终端提示符里。
现有图片按下面的规则处理过，补图时务必沿用同一套，否则同一批图风格不一致：

| 对象 | 处理 | 例 |
|---|---|---|
| 人名 namespace | 露前一半、后一半打星 | `zhangchaowu` → `zhangc*****` |
| 主机 IP | 遮蔽后两段 | `192.168.144.10` → `192.168.*.*` |
| 集群名 | 换成示例名 | `测试集群1` → `production-cluster` |
| 基础组件 namespace | **保留原样** | `kube-system`、`argocd`、`monitoring` |
| 网段常量 / 保留地址 | **保留原样** | `10.0.0.0/8`、`127.0.0.1`、`255.255.255.0` |

几个容易踩的点：

- **替换必须带字母边界**。ns 里既有 `gocd` 又有 `argocd`，裸子串替换会把
  `argocd` 打成 `argo**`，看着像界面出了 bug。用 `(?<![a-z])name(?![a-z])`，
  并按名字从长到短替换（`zhochendongyu` 要早于 `chendongyu`）。
- **网段常量不要打星**。Pod 日志里 ip-masq-agent 会打
  `nonMasqueradeCIDRs:["10.0.0.0/8",...]`，一律遮蔽会截出 `10.0.*.*/8`，
  像是日志查看器把内容弄坏了。判定：带 `/前缀` 且后两段为 0 的是网络地址。
- **改 DOM 文本盖不住三个地方**，只做 TreeWalker 替换会得到"半脱敏"：
  - 仪表盘 ECharts 把节点名画进 `<canvas>`，而本集群节点名**就是 IP**。
    canvas 里的字既改不到、也读不到，得在 metrics 接口的响应体上就改掉。
  - Monaco 的 model 原文不受 DOM 改动影响，一滚动就重新渲染出真名，
    要单独 `setValue()`。
  - 终端里的主机名/路径来自容器本身。最省事的办法是挑 `kube-system`
    下的 Pod 开终端，从源头上避免人名进 xterm。
- **泄漏断言要和脱敏用同一套规则**，否则会自己打自己：读
  `document.body.innerText` 查残留时若不放过上面那些保留项，
  刚故意留下的 `10.0.0.0/8` 会被判成泄漏。canvas 类内容改为读
  ECharts 实例的 option 原始数据来查，并且**找到 0 个实例要算失败**，
  不然这条断言是空过的。

## 增删截图

改了文件名或新增截图，记得同步改主 README 里的 `![描述](docs/screenshots/xxx.png)` 引用，
否则会出现裂图。
