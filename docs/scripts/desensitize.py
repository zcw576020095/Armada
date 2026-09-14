"""README 演示素材的脱敏规则。

规则与 docs/screenshots/README.md 保持一致：人名 namespace 露前一半、主机 IP 遮后两段、
集群名换示例名、私有镜像仓库实例 ID 打星；基础组件 ns、网段常量、公共仓库域名保留原样。

脱敏在网络层做（改响应体），而不是改 DOM —— 因为仪表盘把节点名画进 <canvas>、
Monaco 的 model 原文也不受 DOM 改动影响，只改 DOM 会得到"半脱敏"。
"""

import json
import re
import sqlite3

# 基础组件 / 平台 namespace：人人可见，保留原样才能看出"资源从哪来"
INFRA_NS = {
    'default', 'kube-system', 'kube-public', 'kube-node-lease',
    'argocd', 'monitoring', 'keda', 'promtail', 'jenkins', 'gocd', 'conductor',
    'gatekeeper-system', 'volcano-system', 'mpi-operator', 'kubeflow',
    'cce-monitor', 'cce-node-remedier', 'cprom-system',
    'data-platform', 'haystack', 'haystack-staging',
    'production', 'staging', 'server', 'pre-check',
}

# 集群名与 API Server 地址从库里读，不写死在这里 —— 这个文件要进公开仓库，
# 把真实集群名/公网 IP/私有仓库实例 ID 写成常量，等于让脱敏脚本自己泄露它
# 本该遮住的东西。db.sqlite3 在 .gitignore 里。
CLUSTER_PLACEHOLDER = 'production-cluster'
APISERVER_PLACEHOLDER = '203.0.113.10'   # RFC5737 文档专用地址

# 先粗匹配点分四段、再在回调里判定，而不是把私网前缀写进正则：
# 写成 (?:192\.168|10)(?:\.\d+){3} 时 192\.168 已经吃掉两段、后面却又要三段，
# 结果 192.168.48.108 永远不匹配。跟在 / 后面的按 CIDR 处理，一律不动。
DOTTED_QUAD = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b(?!/)')

# 保留地址：遮了反而让内容失真，像是查看器把日志弄坏了
PRESERVE_IPS = {
    '127.0.0.1', '0.0.0.0',
    '255.255.255.0', '255.255.0.0', '255.0.0.0', '255.255.255.255',
}


def _should_mask_ip(ip):
    """只遮 RFC1918 私网主机地址；网段地址、掩码、回环一律保留。"""
    try:
        octets = [int(p) for p in ip.split('.')]
    except ValueError:
        return False
    if len(octets) != 4 or any(o > 255 for o in octets):
        return False
    if ip in PRESERVE_IPS:
        return False
    if octets[2] == 0 and octets[3] == 0:  # 10.0.0.0 / 192.168.0.0 这类网段地址
        return False
    a, b = octets[0], octets[1]
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


def person_namespaces(db_path):
    """从缓存表里取出人名 namespace（= 全部 ns 减去基础组件白名单）。"""
    conn = sqlite3.connect(db_path)
    rows = list(conn.execute(
        "select data from k8s_resource_cache where resource_type='namespace' "
        "order by id desc limit 1"))
    conn.close()
    if not rows:
        return []
    names = {item.get('name', '') for item in json.loads(rows[0][0])}
    return sorted((n for n in names if n and n not in INFRA_NS),
                  key=len, reverse=True)  # 长名优先，避免 zhochendongyu 被 chendongyu 截断


def _mask_name(name):
    """露前一半、后一半打星。"""
    keep = max(1, len(name) // 2)
    return name[:keep] + '*' * (len(name) - keep)


def cluster_identities(db_path):
    """从库里取集群名与 API Server 主机，返回 [(真实值, 占位值)]。

    这些值不写死在源码里：本文件要进公开仓库，把真实集群名和公网 IP 写成常量
    等于让脱敏脚本自己泄露它本该遮住的东西。
    """
    conn = sqlite3.connect(db_path)
    rows = list(conn.execute('select name, api_server from clusters_cluster'))
    conn.close()

    pairs = []
    for name, api_server in rows:
        if name:
            pairs.append((name, CLUSTER_PLACEHOLDER))
        # 只取 host，端口保留（端口本身不敏感，换掉反而看不出是 6443）
        for host in re.findall(r'//([^:/]+)', api_server or ''):
            if not _should_mask_ip(host):   # 私网地址交给通用 IP 规则处理
                pairs.append((host, APISERVER_PLACEHOLDER))
    return pairs


def build_rules(db_path):
    """返回 [(compiled_pattern, replacement)]，按顺序应用到响应体文本。"""
    rules = []

    for original, replacement in cluster_identities(db_path):
        rules.append((re.compile(re.escape(original)), replacement))

    # 人名 ns：带字母边界，否则 gocd 会把 argocd 打成 argo**。
    # 边界只排除字母（不排除连字符），因为人名会作为 Pod 名前缀出现：
    # aoyuzhuo-actionmesh-eval-4gpu-master-0
    #
    # 129 个名字合并成一条 alternation，而不是逐个 sub 一遍：Pod 列表响应有
    # 1.4MB，逐条跑要 1.9s，合并后 0.22s（8.7 倍）。这不只是快慢问题 ——
    # 录制时拦截器卡 2 秒会让前端在列表渲染完成前就被截图，成片里是空表。
    # 名字按长度降序进 alternation，正则的 | 取最先匹配的分支，
    # 短名在前会让 zhochendongyu 被 chendongyu 截断。
    names = person_namespaces(db_path)
    if names:
        table = {n: _mask_name(n) for n in names}
        rules.append((
            re.compile(r'(?<![a-zA-Z])('
                       + '|'.join(re.escape(n) for n in names)
                       + r')(?![a-zA-Z])'),
            lambda m: table[m.group(1)],
        ))

    # 私有镜像仓库实例 ID：能定位到具体账号下的仓库。公共仓库域名不动。
    rules.append((re.compile(r'\bccr-[0-9a-z]{6,}\b'), 'ccr-********'))
    rules.append((re.compile(r'\bcrpi-[0-9a-z]{6,}\b'), 'crpi-********'))

    def mask_ip(m):
        ip = m.group(0)
        if not _should_mask_ip(ip):
            return ip
        a, b, _, _ = ip.split('.')
        return f'{a}.{b}.*.*'

    rules.append((DOTTED_QUAD, mask_ip))

    return rules


def apply(text, rules):
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


def find_leaks(text, db_path):
    """回读检查：正文里若仍有人名 ns 或未遮蔽的主机 IP 就算泄漏。

    判据复用 _should_mask_ip —— 泄漏断言必须和脱敏共用同一个谓词。
    两边各写一遍私网判定时，一边写错就会让这条断言变成空过（它会"通过"，
    但什么也没查）。
    """
    leaks = []
    for name in person_namespaces(db_path):
        if re.search(r'(?<![a-zA-Z])' + re.escape(name) + r'(?![a-zA-Z])', text):
            leaks.append(f'namespace:{name}')
    for m in DOTTED_QUAD.finditer(text):
        if _should_mask_ip(m.group(0)):
            leaks.append(f'ip:{m.group(0)}')
    # 集群名 / API Server 主机同样从库里取，不写死真实值
    for original, _ in cluster_identities(db_path):
        if original in text:
            leaks.append(f'identity:{original}')
    # 私有仓库实例 ID：未打星的形态（星号本身不含小写字母数字，脱敏后不会再匹配）
    for m in re.finditer(r'\b(?:ccr|crpi)-[0-9a-z]{6,}\b', text):
        leaks.append(f'registry:{m.group(0)}')
    return sorted(set(leaks))
