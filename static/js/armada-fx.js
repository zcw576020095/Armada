/* Armada 视觉层的交互驱动。
   移植自 best-resume 的 web/src/lib/fx.js，同样的分工：
   常驻动效（光晕漂移）+ 交互动效（倾斜/水波/火花/跟随光）。

   所有效果自行处理 prefers-reduced-motion，调用方不用判断。
   本文件只写 CSS 自定义属性和 class、只创建装饰性 DOM，
   不碰任何业务状态（Alpine store / fetch / 表单值）。 */
(function () {
  'use strict';

  var reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasGsap = typeof window.gsap !== 'undefined';

  /* ---------------- 背景光晕 ---------------- */
  /* 三团色斑各自沿不同周期漂移。用 GSAP 而非 CSS keyframes，是为了让每团
     有独立的随机时长与目标点，避免整组同频摆动像钟摆。 */
  function mountBlobs() {
    var host = document.querySelector('.fx-bg');
    if (!host) return;

    var specs = [
      { size: 620, x: '6%', y: '-14%', bg: 'var(--fx-a1)' },
      { size: 540, x: '72%', y: '-6%', bg: 'var(--fx-a2)' },
      { size: 460, x: '40%', y: '46%', bg: 'var(--fx-a3)' }
    ];

    var nodes = specs.map(function (s) {
      var el = document.createElement('i');
      el.className = 'fx-blob';
      el.style.width = el.style.height = s.size + 'px';
      el.style.left = s.x;
      el.style.top = s.y;
      el.style.background = s.bg;
      host.appendChild(el);
      return el;
    });

    if (reduced || !hasGsap) return;

    nodes.forEach(function (el, i) {
      window.gsap.to(el, {
        x: 'random(-140, 140)',
        y: 'random(-90, 110)',
        scale: 'random(0.86, 1.18)',
        duration: 15 + i * 5,
        ease: 'sine.inOut',
        repeat: -1,
        yoyo: true,
        repeatRefresh: true
      });
    });
  }

  /* ---------------- 卡片鼠标跟随光 ---------------- */
  function bindCardGlow() {
    if (reduced) return;
    document.addEventListener(
      'mousemove',
      function (e) {
        if (!e.target || !e.target.closest) return;
        var card = e.target.closest('.fx-card-glow');
        if (!card) return;
        var r = card.getBoundingClientRect();
        card.style.setProperty('--fx-mx', ((e.clientX - r.left) / r.width) * 100 + '%');
        card.style.setProperty('--fx-my', ((e.clientY - r.top) / r.height) * 100 + '%');
      },
      { passive: true }
    );
  }

  /* ---------------- 卡片 3D 倾斜 ---------------- */
  /* 只写 CSS 变量，transform 由 .fx-tilt 在 CSS 里合成 */
  function bindTilt() {
    if (reduced) return;
    var MAX = 6; // 度数超过 6 就开始晃得廉价

    document.addEventListener(
      'mousemove',
      function (e) {
        if (!e.target || !e.target.closest) return;
        var el = e.target.closest('.fx-tilt');
        if (!el) return;
        var r = el.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        el.style.setProperty('--ty', (px * MAX).toFixed(2) + 'deg');
        el.style.setProperty('--tx', (-py * MAX).toFixed(2) + 'deg');
        el.style.setProperty('--tz', '-2px');
      },
      { passive: true }
    );

    document.addEventListener(
      'mouseout',
      function (e) {
        if (!e.target || !e.target.closest) return;
        var el = e.target.closest('.fx-tilt');
        if (!el) return;
        el.style.setProperty('--tx', '0deg');
        el.style.setProperty('--ty', '0deg');
        el.style.setProperty('--tz', '0px');
      },
      { passive: true }
    );
  }

  /* ---------------- 点击水波纹 ---------------- */
  function bindRipple() {
    if (reduced) return;
    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      var el = e.target.closest('.fx-ripple');
      if (!el) return;
      var r = el.getBoundingClientRect();
      var n = document.createElement('span');
      n.className = 'fx-wave';
      n.style.left = e.clientX - r.left + 'px';
      n.style.top = e.clientY - r.top + 'px';
      el.appendChild(n);
      setTimeout(function () {
        n.remove();
      }, 700);
    });
  }

  /* ---------------- 点击火花 ---------------- */
  /* 粒子挂 body 上用 fixed 定位，宿主有 overflow:hidden 也不会被裁掉 */
  function bindSparks() {
    if (reduced || !hasGsap) return;
    var colors = ['var(--color-primary)', 'var(--color-secondary)', 'var(--color-info)'];

    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      if (!e.target.closest('.fx-spark-on')) return;

      var n = 14;
      for (var i = 0; i < n; i++) {
        var p = document.createElement('i');
        p.className = 'fx-spark';
        p.style.left = e.clientX + 'px';
        p.style.top = e.clientY + 'px';
        p.style.background = colors[i % colors.length];
        document.body.appendChild(p);

        var ang = (Math.PI * 2 * i) / n + Math.random() * 0.5;
        var dist = 42 + Math.random() * 58;
        window.gsap.to(p, {
          x: Math.cos(ang) * dist,
          y: Math.sin(ang) * dist + 18, // 略微下坠，像有重力
          opacity: 0,
          scale: 0.2,
          duration: 0.5 + Math.random() * 0.35,
          ease: 'power2.out',
          onComplete: (function (node) {
            return function () {
              node.remove();
            };
          })(p)
        });
      }
    });
  }

  /* ---------------- 标题逐字入场 ---------------- */
  /* 不用 gsap 的 SplitText（付费插件在免费包里不一定带），自己拆字符 */
  function splitTitles() {
    if (reduced || !hasGsap) return;
    document.querySelectorAll('[data-fx-split]').forEach(function (el) {
      if (el.dataset.fxSplitDone) return;
      var text = el.textContent;
      if (!text || text.length > 40) return; // 长文本拆了没意义还伤性能
      el.dataset.fxSplitDone = '1';
      el.textContent = '';
      var chars = [];
      for (var i = 0; i < text.length; i++) {
        var s = document.createElement('span');
        s.className = 'fx-char';
        s.textContent = text[i];
        el.appendChild(s);
        chars.push(s);
      }
      window.gsap.from(chars, {
        y: 14,
        opacity: 0,
        duration: 0.5,
        ease: 'power3.out',
        stagger: 0.024
      });
    });
  }

  /* ---------------- 数字滚动 ---------------- */
  /* 给 [data-fx-count] 的纯数字文本做一次计数补间 */
  function countUp() {
    if (reduced || !hasGsap) return;
    document.querySelectorAll('[data-fx-count]').forEach(function (el) {
      if (el.dataset.fxCountDone) return;
      var raw = (el.textContent || '').trim();
      var target = parseFloat(raw.replace(/,/g, ''));
      if (!isFinite(target) || target === 0) return;
      el.dataset.fxCountDone = '1';
      var isInt = String(raw).indexOf('.') === -1;
      var obj = { v: 0 };
      window.gsap.to(obj, {
        v: target,
        duration: 1.1,
        ease: 'power2.out',
        onUpdate: function () {
          el.textContent = isInt ? Math.round(obj.v) : obj.v.toFixed(1);
        }
      });
    });
  }

  /* ---------------- 顶栏滚动阴影 ---------------- */
  function bindNavShadow() {
    var nav = document.getElementById('topNav');
    if (!nav) return;
    var onScroll = function () {
      nav.classList.toggle('fx-nav-scrolled', window.scrollY > 8);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  function init() {
    mountBlobs();
    bindCardGlow();
    bindTilt();
    bindRipple();
    bindSparks();
    bindNavShadow();
    splitTitles();
    countUp();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* Alpine 异步渲染完内容后可以再调一次，补做拆字/计数 */
  window.armadaFx = { splitTitles: splitTitles, countUp: countUp };
})();
