#!/usr/bin/env python3
"""录制 README 顶部的演示 GIF。

脱敏在网络层做：拦下 HTML / JSON 响应改写响应体，这样 ECharts 画进 canvas 的
节点名、服务端渲染的集群名都能一次盖住，不必再去补 DOM。

帧走 CDP 的 Page.startScreencast(format=png)，**不用 Playwright 的录像**：
录像编码成 VP8 是有损的，同一块 Running 徽章无损截图只有 87 种颜色、webm 抽帧
变成 769 种，多出来的全是压缩噪点 —— 文字边缘发毛、纯色块出现块效应，就是
"动图很模糊"的真正原因（与缩放、调色板都无关，那两处先前都查错了）。
screencast 的 PNG 帧实测回到 87 色，且 1280×800 原尺寸不缩放。

GIF 由 Pillow 合成：Playwright 自带的 ffmpeg 是 --disable-everything 编的，
没有 gif muxer 也没有 palettegen 滤镜。现在整条链路不再需要 ffmpeg。

用法：
    venv/bin/python docs/scripts/record_demo.py
    venv/bin/python docs/scripts/record_demo.py --from-frames /tmp/armada-frames-xxx
"""

import argparse
import base64
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desensitize as ds  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = str(ROOT / 'db.sqlite3')
OUT_DIR = ROOT / 'docs' / 'images'
CHROMIUM = (Path.home() / 'Library/Caches/ms-playwright/chromium-1194'
            / 'chrome-mac/Chromium.app/Contents/MacOS/Chromium')

BASE = 'http://127.0.0.1:9000'
USER, PASSWORD = 'admin', 'admin123'
# 录制视口。不能再缩：资源表格固定要 1009px，1152 视口下内容区只剩 822px，
# 会横向切掉列（1024/900 更糟）。1280 是表格完整显示的下限。
VIEW_W, VIEW_H = 1280, 800

# Playwright 录的视频里没有鼠标指针，不画一个的话画面就是"东西自己在动"，
# 看的人不知道是点了哪里。注入一个跟随 mousemove 的圆点 + 点击涟漪。
CURSOR_JS = r"""
(() => {
  if (window.__armadaCursor) return;
  window.__armadaCursor = true;
  const add = () => {
    if (!document.body) return;
    const dot = document.createElement('div');
    dot.id = '__cursor';
    dot.style.cssText = [
      'position:fixed', 'z-index:2147483647', 'left:0', 'top:0',
      'width:18px', 'height:18px', 'margin:-9px 0 0 -9px',
      'border-radius:50%', 'pointer-events:none',
      'background:rgba(255,255,255,.92)',
      'box-shadow:0 0 0 2px rgba(124,58,237,.9), 0 2px 10px rgba(0,0,0,.45)',
      'transition:transform .08s ease-out', 'opacity:0',
    ].join(';');
    document.body.appendChild(dot);
    document.addEventListener('mousemove', (e) => {
      dot.style.opacity = '1';
      dot.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    }, true);
    document.addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      r.style.cssText = [
        'position:fixed', 'z-index:2147483646', 'pointer-events:none',
        `left:${e.clientX}px`, `top:${e.clientY}px`,
        'width:14px', 'height:14px', 'margin:-7px 0 0 -7px',
        'border-radius:50%', 'border:2px solid rgba(124,58,237,.95)',
      ].join(';');
      document.body.appendChild(r);
      r.animate(
        [{ transform: 'scale(1)', opacity: 1 },
         { transform: 'scale(3.6)', opacity: 0 }],
        { duration: 480, easing: 'ease-out' },
      ).onfinish = () => r.remove();
    }, true);
  };
  if (document.body) add();
  else document.addEventListener('DOMContentLoaded', add);
})();
"""

leaks_seen = set()
masked_hits = 0


def install_desensitizer(context, rules):
    """拦响应改 body。静态资源直接放行，省掉一堆无谓的往返。"""

    def handler(route):
        global masked_hits
        url = route.request.url
        if '/static/' in url or url.endswith(('.css', '.js', '.woff2', '.svg', '.png')):
            return route.continue_()
        try:
            resp = route.fetch()
        except Exception:
            return route.continue_()
        ctype = (resp.headers or {}).get('content-type', '')
        if 'text/html' not in ctype and 'json' not in ctype:
            return route.fulfill(response=resp)
        try:
            original = resp.text()
        except Exception:
            return route.fulfill(response=resp)
        cleaned = ds.apply(original, rules)
        if cleaned != original:
            masked_hits += 1
        for leak in ds.find_leaks(cleaned, DB):
            leaks_seen.add(f'{leak}  <-  {url}')
        # 必须剥掉 Content-Length：脱敏会改变长度（IP 变短、集群名变长），
        # 沿用原 headers 的话浏览器按旧长度截断 JSON，前端解析失败 ——
        # 表现是列表页"暂无数据"、计数 0，而不是报错。
        headers = {k: v for k, v in (resp.headers or {}).items()
                   if k.lower() not in ('content-length', 'content-encoding')}
        return route.fulfill(status=resp.status, headers=headers, body=cleaned)

    context.route('**/*', handler)


def glide(page, x, y, steps=20):
    """插值移动鼠标，让注入的光标看得出轨迹（直接 click 会瞬移）。"""
    state = page.evaluate('() => { const d = document.getElementById("__cursor");'
                          ' return d ? d.style.transform : ""; }')
    m = re.findall(r'-?[\d.]+', state or '')
    cx, cy = (float(m[0]), float(m[1])) if len(m) >= 2 else (VIEW_W / 2, VIEW_H / 2)
    for i in range(1, steps + 1):
        t = i / steps
        ease = 1 - (1 - t) ** 3
        page.mouse.move(cx + (x - cx) * ease, cy + (y - cy) * ease)
        page.wait_for_timeout(9)


def click(page, locator, settle=400):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if not box:
        raise RuntimeError('元素没有 bounding box，可能被遮住了')
    glide(page, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.wait_for_timeout(120)
    locator.click()
    page.wait_for_timeout(settle)


def login(page):
    page.goto(f'{BASE}/accounts/login/', wait_until='networkidle')
    page.fill('input[name="username"]', USER)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')


def select_cluster(page, pk):
    """把当前集群设进 session。

    不设的话侧栏每个资源链接都会走模板里 {% if active_cluster %} 的降级分支、
    统一指向 /clusters/，点「Pods」实际跳到集群列表页 —— 表现为后面找不到
    #searchInput，而不是报"没选集群"。

    next 故意落到 /clusters/ 而不是默认的 /：仪表盘冷启动要拉几百节点的指标，
    重定向过去等 networkidle 会直接超时。
    """
    page.goto(f'{BASE}/clusters/{pk}/select/?next=/clusters/',
              wait_until='domcontentloaded')


def discover_cluster_pk(page):
    """集群 pk 不写死：写死的后果不是报错而是假通过（页面 404、探测拿到空集合）。"""
    page.goto(f'{BASE}/clusters/', wait_until='networkidle')
    hrefs = page.eval_on_selector_all(
        'a[href*="/clusters/"]', 'els => els.map(e => e.getAttribute("href"))')
    for href in hrefs:
        m = re.search(r'/clusters/(\d+)/', href or '')
        if m:
            return m.group(1)
    raise RuntimeError('集群列表里找不到任何 /clusters/<pk>/ 链接')


def record(rules, frame_dir):
    """跑一遍操作流程，把 CDP screencast 的 PNG 帧写进 frame_dir，返回帧路径列表。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM))

        # 登录、选集群、预热都在这个不录像的上下文里做完，再把 cookie 传给
        # 录制上下文 —— 这样成片直接从仪表盘开始，没有登录表单的废镜头。
        warm = browser.new_context(viewport={'width': VIEW_W, 'height': VIEW_H})
        install_desensitizer(warm, rules)
        wp = warm.new_page()
        login(wp)
        pk = discover_cluster_pk(wp)
        select_cluster(wp, pk)
        print(f'集群 pk = {pk}，预热指标与 Pod 列表…')
        t0 = time.time()
        # 直接打指标接口，别走仪表盘页面等 networkidle：几百节点要几十秒，
        # 页面级等待会先超时。缓存是进程内的，必须打到同一个 runserver。
        wp.request.get(f'{BASE}/clusters/{pk}/metrics/', timeout=180_000)
        print(f'  首次拉取 {time.time() - t0:.1f}s')
        wp.goto(f'{BASE}/resources/{pk}/pods/?namespace=kube-system',
                wait_until='domcontentloaded')
        wp.wait_for_timeout(1500)

        # 复测一次确认真的落进缓存了。指标缓存 TTL 只有 60s，而首次拉取本身就要
        # 一分钟左右 —— 稍不注意缓存在录制开始时已经又冷了，那会把几十秒的转圈
        # 直接录进成片（录像从上下文创建就开始，不是从第一次点击开始）。
        t1 = time.time()
        wp.request.get(f'{BASE}/clusters/{pk}/metrics/', timeout=180_000)
        hot = time.time() - t1
        print(f'  复测 {hot:.2f}s')
        if hot > 3:
            raise RuntimeError(
                f'指标复测仍要 {hot:.1f}s，没落进缓存，仪表盘会在录制时转圈')
        state = warm.storage_state()
        warm.close()

        ctx = browser.new_context(
            viewport={'width': VIEW_W, 'height': VIEW_H},
            storage_state=state,
        )
        ctx.add_init_script(CURSOR_JS)
        install_desensitizer(ctx, rules)
        page = ctx.new_page()

        # screencast 从这里开始收帧。先导航到仪表盘再开，避免把 about:blank
        # 那几帧空白收进来（开头的未稳定帧另有 drop_unsettled_head 兜底）。
        page.goto(f'{BASE}/', wait_until='domcontentloaded')
        cast = Screencast(ctx, page, frame_dir)

        # 1) 仪表盘。指标已预热进 60s 缓存，导航在开 screencast 前就做了，
        # 这里只等加载完成 —— 图表轮询会让 networkidle 永远等不到。
        # 判据用 .loading-spinner 这个真正的 spinner 元素是否可见。
        # 两种写法都试错过：等 canvas 出现 —— canvas 在 loading 态就已在 DOM 里，
        # 会在转圈时就往下走；用 textContent.includes 遍历 div —— 匹到的是包含
        # 该文案的最外层父容器，它永远不隐藏，于是干等到超时，把几十秒转圈全录进去。
        try:
            page.wait_for_selector('.loading-spinner', state='hidden', timeout=90_000)
        except Exception:
            print('  !! 仪表盘 spinner 没消失，成片开头会是 loading 态')
        page.wait_for_timeout(2600)

        # 2) Deployment 列表（154 条，秒开）。这里不点 Pods：Pod 列表要在前端
        # 内存里渲染 4700+ 行，成片里会出现近 10 秒的空表干等。
        click(page, page.locator('a.sidebar-nav-item', has_text='Deployments').first,
              settle=600)
        page.wait_for_selector('#resourceTable tbody tr', timeout=60_000)
        page.wait_for_timeout(1600)
        deps = page.locator('#resourceTable tbody tr').count()
        if deps < 2:
            raise RuntimeError(f'Deployment 列表只有 {deps} 行，数据没加载出来')
        print(f'  Deployment 列表 {deps} 行')

        # 3) Pod 列表按 kube-system 预筛。前端会从 ?namespace= 初始化筛选器，
        # payload 和渲染量都降下来，同时避免人名 ns 进画面。
        page.goto(f'{BASE}/resources/{pk}/pods/?namespace=kube-system',
                  wait_until='domcontentloaded')
        page.wait_for_selector('#resourceTable tbody tr', timeout=60_000)
        page.wait_for_timeout(1600)

        # 列表必须真有数据。空表是"假通过"：脚本会一路跑完并产出一个
        # 全程「暂无数据」的废 GIF，而不是报错。
        rows = page.locator('#resourceTable tbody tr').count()
        if rows < 2:
            raise RuntimeError(f'Pod 列表只有 {rows} 行，数据没加载出来，别录了')
        print(f'  Pod 列表 {rows} 行')

        # 4) 搜索 coredns —— 挑 kube-system 的组件，从源头上避免人名进画面
        search = page.locator('#searchInput')
        click(page, search, settle=150)
        search.type('coredns', delay=105)
        page.keyboard.press('Enter')
        page.wait_for_timeout(1400)

        hits = page.locator('#resourceTable tbody tr').count()
        if hits < 1:
            raise RuntimeError('搜 coredns 一行都没有，后面开日志/终端必然点空')
        print(f'  coredns 命中 {hits} 行')

        # 4) 日志
        click(page, page.locator('button[title="日志"]').first, settle=400)
        page.wait_for_timeout(1900)
        page.keyboard.press('Escape')
        page.wait_for_timeout(400)

        # 5) 容器终端：浏览器内直连 shell
        click(page, page.locator('button[title="终端"]').first, settle=500)
        page.wait_for_timeout(1900)
        page.keyboard.type('ls /', delay=110)
        page.wait_for_timeout(260)
        page.keyboard.press('Enter')
        page.wait_for_timeout(2100)

        cast.stop()
        measured_fps = cast.fps
        frame_paths = cast.paths
        ctx.close()
        browser.close()

    print(f'  screencast 收到 {len(frame_paths)} 帧（{measured_fps:.0f} fps）')
    return frame_paths, measured_fps


class Screencast:
    """CDP Page.startScreencast(format=png) 的帧收集器。

    必须显式给 maxWidth/maxHeight，否则 CDP 会自行缩放输出 ——
    那就又回到"缩放糊字"的老问题上。
    """

    def __init__(self, ctx, page, frame_dir):
        self.dir = frame_dir
        self.paths = []
        self._t0 = time.time()
        self._client = ctx.new_cdp_session(page)
        self._client.on('Page.screencastFrame', self._on_frame)
        self._client.send('Page.startScreencast', {
            'format': 'png', 'everyNthFrame': 1,
            'maxWidth': VIEW_W, 'maxHeight': VIEW_H,
        })

    def _on_frame(self, params):
        path = self.dir / f'{len(self.paths):05d}.png'
        path.write_bytes(base64.b64decode(params['data']))
        self.paths.append(path)
        try:
            # 不 Ack 的话 Chromium 会停发后续帧
            self._client.send('Page.screencastFrameAck',
                              {'sessionId': params['sessionId']})
        except Exception:
            pass

    def stop(self):
        self._elapsed = time.time() - self._t0
        try:
            self._client.send('Page.stopScreencast')
        except Exception:
            pass

    @property
    def count(self):
        return len(self.paths)

    @property
    def fps(self):
        el = getattr(self, '_elapsed', None) or (time.time() - self._t0)
        return len(self.paths) / el if el else 0


def resample(frames, target_fps, source_fps):
    """screencast 是变帧率（有变化才发帧），按时间均匀抽到目标帧率。

    直接每 N 帧取一帧会让"页面静止时"和"动画密集时"的实际时间被压成一样，
    动图节奏会失真。这里按累计时间取最近帧。
    """
    if not frames or target_fps >= source_fps:
        return frames
    step = source_fps / target_fps
    picked, i = [], 0.0
    while i < len(frames):
        picked.append(frames[int(i)])
        i += step
    return picked


def drop_unsettled_head(frames, lookahead=4, tol=0.012):
    """裁掉开头没稳定下来的帧。

    GitHub 拿首帧当封面，所以首帧必须是一张"页面已经长好"的图。开头这段要裁掉的
    东西不止白屏：还有 Alpine 初始化前的 FOUC（该隐藏的下拉菜单全部展开）、
    骨架屏的粉色 shimmer、GSAP 入场动画。

    判据是"稳定"而不是"够暗/够花" —— 我先用亮度+颜色数的启发式判过，它把
    骨架屏那帧判成了正常内容。改成找第一个和它 lookahead 帧之后几乎一样的帧：
    动画在动就不稳定，长好了才稳定。
    """
    from PIL import Image, ImageChops

    def thumb(path):
        return Image.open(path).convert('RGB').resize((96, 60), Image.BILINEAR)

    for i in range(len(frames) - lookahead):
        a, b = thumb(frames[i]), thumb(frames[i + lookahead])
        diff = ImageChops.difference(a, b)
        # 平均绝对差归一化到 0~1
        score = sum(sum(px) for px in diff.getdata()) / (96 * 60 * 3 * 255)
        if score < tol:
            return frames[i:], i
    return frames, 0


def build_gif(frames, out, colors, delay, diff_thresh):
    """用一张共享调色板量化所有帧。

    每帧各自量化时，同一块没变的区域会落到不同的调色板索引上，帧间就压不动了
    （实测 37MB vs 5.5MB）。disposal 必须是 1：用 2 会让每帧都先恢复背景，
    同样毁掉帧间压缩（25MB vs 5.5MB）。
    """
    from PIL import Image, ImageChops

    def load(path):
        return Image.open(path).convert('RGB')

    # 主调色板从整段均匀取样，不能只用首帧 —— 否则后面才出现的颜色
    # （终端里的绿字等）没进调色板，会偏色。
    probe = [load(f) for f in frames[::max(1, len(frames) // 14)]]
    strip = Image.new('RGB', (probe[0].width, probe[0].height * len(probe)))
    for i, im in enumerate(probe):
        strip.paste(im, (0, i * probe[0].height))
    master = strip.quantize(colors=colors, method=Image.MEDIANCUT)

    imgs, delays, prev = [], [], None
    for f in frames:
        im = load(f)
        if prev is not None:
            bbox = ImageChops.difference(im, prev).getbbox()
            area = 0 if bbox is None else (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            if area < diff_thresh:      # 画面基本没动：并进上一帧、延长停留
                delays[-1] += delay
                continue
        imgs.append(im.quantize(palette=master, dither=Image.NONE))
        delays.append(delay)
        prev = im

    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=delays,
                 loop=0, optimize=True, disposal=1)
    return len(imgs), sum(delays) / 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fps', type=int, default=9)
    # 200 色：背景是大面积紫色径向渐变光晕，正是量化的最坏情况。128 色会压出
    # 蓝/青/红的色阶断层，看着像图片坏了。加调色板比开抖动划算 —— 抖动撒的噪点
    # 会打断 LZW 的行程，体积涨得更多。
    ap.add_argument('--colors', type=int, default=200)
    ap.add_argument('--diff-thresh', type=int, default=800)
    ap.add_argument('--max-seconds', type=int, default=60,
                    help='成片时长上限，超了就报错而不是产出废 GIF')
    ap.add_argument('--from-frames',
                    help='跳过录制，用现成的帧目录重新合成 GIF')
    ap.add_argument('--source-fps', type=float, default=70,
                    help='配合 --from-frames：原始帧的采集帧率（screencast 实测约 70）')
    ap.add_argument('--keep-frames', action='store_true',
                    help='保留原始 PNG 帧，便于反复调参数不重录')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rules = ds.build_rules(DB)
    print(f'脱敏规则 {len(rules)} 条（人名 ns {len(ds.person_namespaces(DB))} 个）')

    if args.from_frames:
        frame_dir = Path(args.from_frames)
        frames = sorted(frame_dir.glob('*.png'))
        cleanup = False
        source_fps = args.source_fps
    else:
        frame_dir = Path(tempfile.mkdtemp(prefix='armada-frames-'))
        cleanup = not args.keep_frames
        frames, source_fps = record(rules, frame_dir)
        print(f'\n改写过的响应 {masked_hits} 个')
        if masked_hits == 0:
            print('!! 一次都没改到，脱敏等于没跑，先查规则再发布')
            return 1
        if leaks_seen:
            print(f'!! 回读发现 {len(leaks_seen)} 处残留：')
            for item in sorted(leaks_seen)[:25]:
                print('   ', item)
            return 1
        print('回读无残留')

    gif = OUT_DIR / 'demo.gif'
    try:
        if not frames:
            print('!! 一帧都没收到，screencast 没工作')
            return 1
        frames, dropped = drop_unsettled_head(frames)
        if dropped:
            print(f'裁掉开头 {dropped} 帧未稳定画面')

        # screencast 是变帧率的（只在画面有变化时发帧），实测约 70fps。
        # 按实测帧率抽到目标帧率，别每 N 帧硬取一帧。
        kept_src = len(frames)
        frames = resample(frames, args.fps, max(args.fps, source_fps))
        print(f'{kept_src} 帧 -> 抽为 {len(frames)} 帧，合成 GIF…')

        # 护栏：某个等待卡住时（曾因判据写错干等 180s），会安静产出一个
        # 200 秒 / 27MB 的废 GIF。宁可报错也别发这种东西。
        if len(frames) > args.max_seconds * args.fps:
            print(f'!! 成片会有 {len(frames) / args.fps:.0f}s，超过 '
                  f'{args.max_seconds}s 上限，说明某处在干等，别合成了')
            return 1

        kept, secs = build_gif(frames, gif, args.colors,
                               round(1000 / args.fps), args.diff_thresh)
    finally:
        if cleanup:
            shutil.rmtree(frame_dir, ignore_errors=True)
        else:
            print(f'原始帧保留在 {frame_dir}')

    size_mb = gif.stat().st_size / 1024 / 1024
    print(f'\n{gif.relative_to(ROOT)}  {kept} 帧 / {secs:.1f}s / {size_mb:.2f} MB')
    if size_mb > 8:
        print('   偏大，建议降 --fps 或缩短流程')
    return 0


if __name__ == '__main__':
    sys.exit(main())
