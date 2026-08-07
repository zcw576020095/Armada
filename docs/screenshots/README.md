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

## 截图建议

- 浏览器窗口 **1600×1000** 左右，和项目验证脚本用的视口一致
- 主题任选，但**同一批保持一致**（要么全深色要么全浅色），混着看很乱
- 弹窗类截图（终端 / 日志 / 回滚 / 校验）建议连带背景页面一起截，能看出上下文
- 保存为 PNG，直接放进本目录

## 注意脱敏

截图会公开在 GitHub 上，注意这几处：

- 集群名、节点 IP、API Server 地址
- 命名空间和 Pod 名里的项目代号 / 人名
- 终端截图里的主机名、路径、环境变量
- 用户管理页的真实用户名

不方便露出的，截图前先在界面上改成示例值，或截完用图片工具涂掉。

## 增删截图

改了文件名或新增截图，记得同步改主 README 里的 `![描述](docs/screenshots/xxx.png)` 引用，
否则会出现裂图。
