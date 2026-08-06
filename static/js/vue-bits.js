/* ============================================================
   vue-bits 组件移植层 — 行为部分
   源: https://github.com/DavidHDev/vue-bits  (src/content/**)

   每个组件保留原版的算法与数值（邻近度公式、惯性积分、噪声参数等），
   只把 Vue 的响应式外壳换成「扫描 data-vb-* 属性 + 原生事件」。

   约定：
     · 全部效果自行判断 prefers-reduced-motion，调用方不用管
     · 只写 CSS 自定义属性 / class / 装饰性 DOM，不碰业务状态
     · Alpine 异步渲染完可以再调 window.vueBits.refresh() 补挂载
     · 已挂载的节点打 data-vb-done，refresh() 不会重复绑
   ============================================================ */
(function () {
  'use strict';

  var reduced =
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasGsap = typeof window.gsap !== 'undefined';
  var isMobile = window.innerWidth <= 768;

  function each(sel, fn) {
    Array.prototype.forEach.call(document.querySelectorAll(sel), fn);
  }

  /* 幂等标记：同一元素同一效果只绑一次。Alpine 重渲染后 refresh() 靠这个去重。 */
  function claim(el, key) {
    var k = 'vb' + key;
    if (el.dataset[k]) return false;
    el.dataset[k] = '1';
    return true;
  }

  /* ============================================================
     MagicBento — Components/MagicBento/MagicBento.vue
     原版三件套：全局聚光灯、邻近度边框辉光、hover 粒子。
     邻近度是精髓：proximity = radius*0.5，fadeDistance = radius*0.75，
     距离在两者之间时线性插值，于是整片卡片墙有亮度梯度，不是单卡 hover。
     ============================================================ */
  var BENTO_RADIUS = 300;
  var BENTO_PARTICLES = 10;

  function bentoProximity(radius) {
    return { proximity: radius * 0.5, fadeDistance: radius * 0.75 };
  }

  function mountBento() {
    var sections = document.querySelectorAll('[data-vb-bento]');
    if (!sections.length || reduced || isMobile) return;

    var spotlight = document.querySelector('.vb-spotlight');
    if (!spotlight) {
      spotlight = document.createElement('div');
      spotlight.className = 'vb-spotlight';
      document.body.appendChild(spotlight);
    }

    if (!claim(document.body, 'BentoBound')) return;

    document.addEventListener(
      'mousemove',
      function (e) {
        var inAny = false;

        Array.prototype.forEach.call(sections, function (section) {
          var rect = section.getBoundingClientRect();
          var inside =
            e.clientX >= rect.left &&
            e.clientX <= rect.right &&
            e.clientY >= rect.top &&
            e.clientY <= rect.bottom;

          var cards = section.querySelectorAll('.vb-bento-card');
          if (!inside) {
            Array.prototype.forEach.call(cards, function (card) {
              card.style.setProperty('--vb-glow-intensity', '0');
            });
            return;
          }

          inAny = true;
          var t = bentoProximity(BENTO_RADIUS);
          var minDistance = Infinity;

          Array.prototype.forEach.call(cards, function (card) {
            var cr = card.getBoundingClientRect();
            var cx = cr.left + cr.width / 2;
            var cy = cr.top + cr.height / 2;
            // 减去半个卡片尺寸：让"贴着卡片边"就算距离 0，而不是要碰到中心
            var d =
              Math.hypot(e.clientX - cx, e.clientY - cy) - Math.max(cr.width, cr.height) / 2;
            var eff = Math.max(0, d);
            minDistance = Math.min(minDistance, eff);

            var glow = 0;
            if (eff <= t.proximity) {
              glow = 1;
            } else if (eff <= t.fadeDistance) {
              glow = (t.fadeDistance - eff) / (t.fadeDistance - t.proximity);
            }

            card.style.setProperty(
              '--vb-glow-x',
              ((e.clientX - cr.left) / cr.width) * 100 + '%'
            );
            card.style.setProperty(
              '--vb-glow-y',
              ((e.clientY - cr.top) / cr.height) * 100 + '%'
            );
            card.style.setProperty('--vb-glow-intensity', String(glow));
            card.style.setProperty('--vb-glow-radius', BENTO_RADIUS + 'px');
          });

          var opacity =
            minDistance <= t.proximity
              ? 0.8
              : minDistance <= t.fadeDistance
                ? ((t.fadeDistance - minDistance) / (t.fadeDistance - t.proximity)) * 0.8
                : 0;

          if (hasGsap) {
            window.gsap.to(spotlight, {
              left: e.clientX,
              top: e.clientY,
              duration: 0.1,
              ease: 'power2.out'
            });
            window.gsap.to(spotlight, {
              opacity: opacity,
              duration: opacity > 0 ? 0.2 : 0.5,
              ease: 'power2.out'
            });
          } else {
            spotlight.style.left = e.clientX + 'px';
            spotlight.style.top = e.clientY + 'px';
            spotlight.style.opacity = String(opacity);
          }
        });

        if (!inAny) {
          if (hasGsap) {
            window.gsap.to(spotlight, { opacity: 0, duration: 0.3, ease: 'power2.out' });
          } else {
            spotlight.style.opacity = '0';
          }
        }
      },
      { passive: true }
    );

    // 鼠标移出文档时收干净，否则聚光灯会停在最后位置
    document.addEventListener('mouseleave', function () {
      each('.vb-bento-card', function (card) {
        card.style.setProperty('--vb-glow-intensity', '0');
      });
      spotlight.style.opacity = '0';
    });
  }

  /* hover 粒子。原版按 index*100ms 依次冒出，不是一次全喷 */
  function bindBentoParticles() {
    if (reduced || isMobile || !hasGsap) return;

    each('.vb-bento-card', function (card) {
      if (!claim(card, 'Particles')) return;

      var live = [];
      var timers = [];
      var hovered = false;

      card.addEventListener('mouseenter', function () {
        hovered = true;
        var rect = card.getBoundingClientRect();

        for (var i = 0; i < BENTO_PARTICLES; i++) {
          timers.push(
            setTimeout(
              (function (bx, by) {
                return function () {
                  if (!hovered) return;
                  var p = document.createElement('i');
                  p.className = 'vb-particle';
                  p.style.left = bx + 'px';
                  p.style.top = by + 'px';
                  card.appendChild(p);
                  live.push(p);

                  window.gsap.fromTo(
                    p,
                    { scale: 0, opacity: 0 },
                    { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' }
                  );
                  window.gsap.to(p, {
                    x: (Math.random() - 0.5) * 100,
                    y: (Math.random() - 0.5) * 100,
                    rotation: Math.random() * 360,
                    duration: 2 + Math.random() * 2,
                    ease: 'none',
                    repeat: -1,
                    yoyo: true
                  });
                  window.gsap.to(p, {
                    opacity: 0.3,
                    duration: 1.5,
                    ease: 'power2.inOut',
                    repeat: -1,
                    yoyo: true
                  });
                };
              })(Math.random() * rect.width, Math.random() * rect.height),
              i * 100
            )
          );
        }
      });

      card.addEventListener('mouseleave', function () {
        hovered = false;
        timers.forEach(clearTimeout);
        timers = [];
        live.forEach(function (p) {
          window.gsap.to(p, {
            scale: 0,
            opacity: 0,
            duration: 0.3,
            ease: 'back.in(1.7)',
            onComplete: function () {
              if (p.parentNode) p.parentNode.removeChild(p);
            }
          });
        });
        live = [];
      });
    });
  }

  /* ============================================================
     SpotlightCard — Components/SpotlightCard/SpotlightCard.vue
     ============================================================ */
  function bindSpotlightCards() {
    if (reduced) return;
    document.addEventListener(
      'mousemove',
      function (e) {
        if (!e.target || !e.target.closest) return;
        var el = e.target.closest('.vb-spotlight-card');
        if (!el) return;
        var r = el.getBoundingClientRect();
        // 原版用 px 而非 %：光斑不随卡片长宽比拉扁
        el.style.setProperty('--vb-sx', e.clientX - r.left + 'px');
        el.style.setProperty('--vb-sy', e.clientY - r.top + 'px');
      },
      { passive: true }
    );
  }

  /* ============================================================
     GlareHover — Animations/GlareHover.vue
     必须先无过渡复位到 -100%，强制 reflow，再设 100% 才能重复触发。
     纯 CSS 做不到这点（transition 不会因为 class 移除又加上而重放）。
     ============================================================ */
  function bindGlare() {
    if (reduced) return;

    each('.vb-glare', function (el) {
      if (!claim(el, 'Glare')) return;

      var overlay = el.querySelector('.vb-glare-overlay');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'vb-glare-overlay';
        el.appendChild(overlay);
      }

      el.addEventListener('mouseenter', function () {
        overlay.style.transition = 'none';
        overlay.style.backgroundPosition = '-100% -100%';
        void overlay.offsetHeight; // 强制 reflow，让上一行立即生效
        overlay.style.transition = '650ms ease';
        overlay.style.backgroundPosition = '100% 100%';
      });

      el.addEventListener('mouseleave', function () {
        overlay.style.transition = '650ms ease';
        overlay.style.backgroundPosition = '-100% -100%';
      });
    });
  }

  /* ============================================================
     Magnet — Animations/Magnet.vue
     鼠标进入 padding 范围就朝鼠标偏移 distance/strength
     ============================================================ */
  function bindMagnets() {
    if (reduced || isMobile) return;

    var magnets = document.querySelectorAll('.vb-magnet');
    if (!magnets.length) return;
    if (!claim(document.body, 'MagnetBound')) return;

    document.addEventListener(
      'mousemove',
      function (e) {
        each('.vb-magnet', function (el) {
          var padding = parseFloat(el.dataset.vbMagnetPadding || '80');
          var strength = parseFloat(el.dataset.vbMagnetStrength || '3');
          var r = el.getBoundingClientRect();
          var cx = r.left + r.width / 2;
          var cy = r.top + r.height / 2;

          if (
            Math.abs(cx - e.clientX) < r.width / 2 + padding &&
            Math.abs(cy - e.clientY) < r.height / 2 + padding
          ) {
            el.dataset.vbMagnetActive = '1';
            el.style.setProperty('--vb-mag-x', (e.clientX - cx) / strength + 'px');
            el.style.setProperty('--vb-mag-y', (e.clientY - cy) / strength + 'px');
          } else if (el.dataset.vbMagnetActive === '1') {
            el.dataset.vbMagnetActive = '0';
            el.style.setProperty('--vb-mag-x', '0px');
            el.style.setProperty('--vb-mag-y', '0px');
          }
        });
      },
      { passive: true }
    );
  }

  /* ============================================================
     ClickSpark — Animations/ClickSpark.vue
     8 条线段从点击点向外飞并缩短。原版每个容器一块 canvas 常驻 rAF；
     这里全局共用一块 fixed canvas，且没有火花时就停掉 rAF。
     ============================================================ */
  var sparkCanvas = null;
  var sparks = [];
  var sparkRaf = null;

  function ensureSparkCanvas() {
    if (sparkCanvas) return sparkCanvas;
    sparkCanvas = document.createElement('canvas');
    sparkCanvas.style.cssText =
      'position:fixed;inset:0;pointer-events:none;z-index:9998;';
    document.body.appendChild(sparkCanvas);

    var resize = function () {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      sparkCanvas.width = window.innerWidth * dpr;
      sparkCanvas.height = window.innerHeight * dpr;
      sparkCanvas.style.width = window.innerWidth + 'px';
      sparkCanvas.style.height = window.innerHeight + 'px';
      sparkCanvas.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);
    return sparkCanvas;
  }

  function sparkColor() {
    var probe = getComputedStyle(document.documentElement).getPropertyValue('--color-primary');
    return (probe || '#22d3ee').trim();
  }

  function drawSparks(ts) {
    var ctx = sparkCanvas.getContext('2d');
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

    var DURATION = 400;
    var RADIUS = 18;
    var SIZE = 11;

    sparks = sparks.filter(function (s) {
      var elapsed = ts - s.t;
      if (elapsed >= DURATION) return false;

      var p = elapsed / DURATION;
      var eased = p * (2 - p); // ease-out，同原版默认
      var dist = eased * RADIUS;
      var len = SIZE * (1 - eased);

      ctx.strokeStyle = s.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(s.x + dist * Math.cos(s.a), s.y + dist * Math.sin(s.a));
      ctx.lineTo(s.x + (dist + len) * Math.cos(s.a), s.y + (dist + len) * Math.sin(s.a));
      ctx.stroke();
      return true;
    });

    if (sparks.length) {
      sparkRaf = requestAnimationFrame(drawSparks);
    } else {
      sparkRaf = null; // 空转就停，别让一块全屏 canvas 白烧 60fps
    }
  }

  function bindClickSpark() {
    if (reduced) return;
    if (!claim(document.body, 'SparkBound')) return;

    document.addEventListener('click', function (e) {
      if (!e.target || !e.target.closest) return;
      if (!e.target.closest('[data-vb-spark]')) return;

      ensureSparkCanvas();
      var color = sparkColor();
      var COUNT = 8;
      for (var i = 0; i < COUNT; i++) {
        sparks.push({
          x: e.clientX,
          y: e.clientY,
          a: (2 * Math.PI * i) / COUNT,
          t: performance.now(),
          color: color
        });
      }
      if (sparkRaf === null) sparkRaf = requestAnimationFrame(drawSparks);
    });
  }

  /* ============================================================
     DotGrid — Backgrounds/DotGrid/DotGrid.vue
     点阵按离鼠标的距离在 base/active 两色间插值；快速划过或点击时
     点被推开再弹回。

     原版用 GSAP 的 InertiaPlugin 做推开-回弹，那是付费插件，免费包里没有。
     这里自己写：推开给初速度，每帧按 resistance 做指数衰减积分，
     速度衰减到阈值以下再用弹性缓动拉回原位。观感等价。
     ============================================================ */
  function mountDotGrids() {
    each('[data-vb-dotgrid]', function (host) {
      if (!claim(host, 'DotGrid')) return;

      var canvas = document.createElement('canvas');
      canvas.style.cssText =
        'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;';
      host.appendChild(canvas);

      var ctx = canvas.getContext('2d');
      if (!ctx) return;

      var DOT = parseFloat(host.dataset.vbDotSize || '4');
      var GAP = parseFloat(host.dataset.vbDotGap || '26');
      var PROXIMITY = parseFloat(host.dataset.vbDotProximity || '130');
      var SPEED_TRIGGER = 100;
      var SHOCK_RADIUS = 240;
      var SHOCK_STRENGTH = 5;
      var MAX_SPEED = 5000;
      var RESISTANCE = 750;
      var RETURN_MS = 1500;

      var dots = [];
      var baseRgb = { r: 120, g: 130, b: 150 };
      var activeRgb = { r: 34, g: 211, b: 238 };

      /* 主题色是 oklch()，canvas 的 fillStyle 不认，借一个隐藏节点让浏览器
         算成 rgb 再读回来。主题切换后需重新采样。 */
      function sampleColors() {
        var probe = document.createElement('span');
        probe.style.cssText = 'position:absolute;opacity:0;pointer-events:none;';
        document.body.appendChild(probe);

        probe.style.color = 'var(--color-primary)';
        activeRgb = parseRgb(getComputedStyle(probe).color) || activeRgb;

        probe.style.color =
          'color-mix(in oklab, var(--color-base-content) 22%, var(--color-base-200))';
        baseRgb = parseRgb(getComputedStyle(probe).color) || baseRgb;

        document.body.removeChild(probe);
      }

      function parseRgb(str) {
        var m = /rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/.exec(str || '');
        if (!m) return null;
        return { r: +m[1], g: +m[2], b: +m[3] };
      }

      function build() {
        var rect = host.getBoundingClientRect();
        if (!rect.width || !rect.height) return;

        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        var cell = DOT + GAP;
        var cols = Math.floor((rect.width + GAP) / cell);
        var rows = Math.floor((rect.height + GAP) / cell);
        var startX = (rect.width - (cell * cols - GAP)) / 2 + DOT / 2;
        var startY = (rect.height - (cell * rows - GAP)) / 2 + DOT / 2;

        dots = [];
        for (var y = 0; y < rows; y++) {
          for (var x = 0; x < cols; x++) {
            dots.push({
              cx: startX + x * cell,
              cy: startY + y * cell,
              ox: 0,
              oy: 0,
              vx: 0,
              vy: 0,
              returning: 0 // >0 时是回弹剩余毫秒
            });
          }
        }
      }

      var pointer = { x: -9999, y: -9999, vx: 0, vy: 0, speed: 0, lt: 0, lx: 0, ly: 0 };
      var raf = null;
      var lastFrame = 0;

      function frame(ts) {
        var rect = host.getBoundingClientRect();
        var dt = lastFrame ? Math.min((ts - lastFrame) / 1000, 0.05) : 0.016;
        lastFrame = ts;

        ctx.clearRect(0, 0, rect.width, rect.height);
        var proxSq = PROXIMITY * PROXIMITY;
        var moving = false;

        for (var i = 0; i < dots.length; i++) {
          var d = dots[i];

          // 惯性积分：指数衰减，替代 InertiaPlugin
          if (d.vx || d.vy) {
            d.ox += d.vx * dt;
            d.oy += d.vy * dt;
            var decay = Math.exp((-RESISTANCE / 260) * dt);
            d.vx *= decay;
            d.vy *= decay;
            if (Math.hypot(d.vx, d.vy) < 6) {
              d.vx = d.vy = 0;
              d.returning = RETURN_MS;
              d.rx = d.ox;
              d.ry = d.oy;
              d.rt = 0;
            }
            moving = true;
          } else if (d.returning > 0) {
            d.rt += dt * 1000;
            var t = Math.min(d.rt / RETURN_MS, 1);
            // elastic.out(1, 0.75) 的等价实现
            var e =
              t >= 1
                ? 1
                : 1 - Math.pow(2, -10 * t) * Math.cos(((t * 10 - 0.75) * (2 * Math.PI)) / 3);
            d.ox = d.rx * (1 - e);
            d.oy = d.ry * (1 - e);
            if (t >= 1) {
              d.returning = 0;
              d.ox = d.oy = 0;
            }
            moving = true;
          }

          var dx = d.cx - pointer.x;
          var dy = d.cy - pointer.y;
          var dsq = dx * dx + dy * dy;

          var r = baseRgb.r;
          var g = baseRgb.g;
          var b = baseRgb.b;
          if (dsq <= proxSq) {
            var k = 1 - Math.sqrt(dsq) / PROXIMITY;
            r = Math.round(baseRgb.r + (activeRgb.r - baseRgb.r) * k);
            g = Math.round(baseRgb.g + (activeRgb.g - baseRgb.g) * k);
            b = Math.round(baseRgb.b + (activeRgb.b - baseRgb.b) * k);
          }

          ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
          ctx.beginPath();
          ctx.arc(d.cx + d.ox, d.cy + d.oy, DOT / 2, 0, Math.PI * 2);
          ctx.fill();
        }

        // 鼠标不在范围内、也没有点在动，就停 rAF；下次交互再拉起来
        var idle = pointer.x < -1000 && !moving;
        if (idle) {
          raf = null;
          return;
        }
        raf = requestAnimationFrame(frame);
      }

      function kick() {
        if (raf === null) {
          lastFrame = 0;
          raf = requestAnimationFrame(frame);
        }
      }

      function push(d, cx, cy, extraVx, extraVy, strength) {
        var dist = Math.hypot(d.cx - cx, d.cy - cy);
        var falloff = Math.max(0, 1 - dist / SHOCK_RADIUS);
        d.returning = 0;
        d.vx = (d.cx - cx) * strength * falloff + extraVx;
        d.vy = (d.cy - cy) * strength * falloff + extraVy;
      }

      var lastMove = 0;
      function onMove(e) {
        var now = performance.now();
        if (now - lastMove < 50) return; // 原版 throttle 50ms
        lastMove = now;

        var dt = pointer.lt ? now - pointer.lt : 16;
        var vx = ((e.clientX - pointer.lx) / dt) * 1000;
        var vy = ((e.clientY - pointer.ly) / dt) * 1000;
        var speed = Math.hypot(vx, vy);
        if (speed > MAX_SPEED) {
          var s = MAX_SPEED / speed;
          vx *= s;
          vy *= s;
          speed = MAX_SPEED;
        }
        pointer.lt = now;
        pointer.lx = e.clientX;
        pointer.ly = e.clientY;

        var rect = host.getBoundingClientRect();
        var inside =
          e.clientX >= rect.left &&
          e.clientX <= rect.right &&
          e.clientY >= rect.top &&
          e.clientY <= rect.bottom;

        pointer.x = inside ? e.clientX - rect.left : -9999;
        pointer.y = inside ? e.clientY - rect.top : -9999;

        if (inside && speed > SPEED_TRIGGER) {
          for (var i = 0; i < dots.length; i++) {
            var d = dots[i];
            if (Math.hypot(d.cx - pointer.x, d.cy - pointer.y) < PROXIMITY && !d.vx && !d.vy) {
              push(d, pointer.x, pointer.y, vx * 0.12, vy * 0.12, 1.6);
            }
          }
        }
        kick();
      }

      function onClick(e) {
        var rect = host.getBoundingClientRect();
        if (
          e.clientX < rect.left ||
          e.clientX > rect.right ||
          e.clientY < rect.top ||
          e.clientY > rect.bottom
        )
          return;
        var cx = e.clientX - rect.left;
        var cy = e.clientY - rect.top;
        for (var i = 0; i < dots.length; i++) {
          var d = dots[i];
          if (Math.hypot(d.cx - cx, d.cy - cy) < SHOCK_RADIUS) {
            push(d, cx, cy, 0, 0, SHOCK_STRENGTH);
          }
        }
        kick();
      }

      sampleColors();
      build();
      kick();

      if ('ResizeObserver' in window) {
        new ResizeObserver(function () {
          build();
          kick();
        }).observe(host);
      }

      if (!reduced) {
        window.addEventListener('mousemove', onMove, { passive: true });
        window.addEventListener('click', onClick);
      }

      // 主题切换后 oklch 变了，重新采样
      new MutationObserver(function () {
        sampleColors();
        kick();
      }).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme']
      });
    });
  }

  /* ============================================================
     LetterGlitch — Backgrounds/LetterGlitch/LetterGlitch.vue
     字符矩阵，每帧随机替换 5% 的格子，颜色在候选色间平滑过渡。
     ============================================================ */
  var GLITCH_CHARS =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$&*()-_+=/[]{};:<>,0123456789'.split('');

  function mountLetterGlitch() {
    each('[data-vb-glitch]', function (host) {
      if (!claim(host, 'Glitch')) return;

      var canvas = document.createElement('canvas');
      canvas.style.cssText =
        'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;';
      host.appendChild(canvas);

      var ctx = canvas.getContext('2d');
      if (!ctx) return;

      var FONT = 14;
      var CW = 9;
      var CH = 18;
      var SPEED = parseFloat(host.dataset.vbGlitchSpeed || '55');

      var letters = [];
      var cols = 0;
      var palette = [
        [40, 70, 60],
        [97, 220, 163],
        [97, 179, 220]
      ];

      function samplePalette() {
        var probe = document.createElement('span');
        probe.style.cssText = 'position:absolute;opacity:0;pointer-events:none;';
        document.body.appendChild(probe);
        var out = [];
        ['--color-primary', '--color-info', '--color-secondary'].forEach(function (tok) {
          probe.style.color = 'color-mix(in oklab, var(' + tok + ') 62%, var(--color-base-200))';
          var m = /rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/.exec(
            getComputedStyle(probe).color
          );
          if (m) out.push([+m[1], +m[2], +m[3]]);
        });
        document.body.removeChild(probe);
        if (out.length) palette = out;
      }

      function pickChar() {
        return GLITCH_CHARS[(Math.random() * GLITCH_CHARS.length) | 0];
      }
      function pickColor() {
        return palette[(Math.random() * palette.length) | 0];
      }

      function build() {
        var rect = host.getBoundingClientRect();
        if (!rect.width || !rect.height) return;

        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        cols = Math.ceil(rect.width / CW);
        var rows = Math.ceil(rect.height / CH);
        letters = [];
        for (var i = 0; i < cols * rows; i++) {
          var c = pickColor();
          letters.push({ ch: pickChar(), c: c.slice(), target: c, p: 1 });
        }
      }

      function draw() {
        var rect = host.getBoundingClientRect();
        ctx.clearRect(0, 0, rect.width, rect.height);
        ctx.font = FONT + 'px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.textBaseline = 'top';
        for (var i = 0; i < letters.length; i++) {
          var l = letters[i];
          ctx.fillStyle = 'rgb(' + (l.c[0] | 0) + ',' + (l.c[1] | 0) + ',' + (l.c[2] | 0) + ')';
          ctx.fillText(l.ch, (i % cols) * CW, ((i / cols) | 0) * CH);
        }
      }

      var last = 0;
      var raf = null;

      function loop(ts) {
        if (ts - last >= SPEED) {
          last = ts;
          var n = Math.max(1, (letters.length * 0.05) | 0);
          for (var i = 0; i < n; i++) {
            var l = letters[(Math.random() * letters.length) | 0];
            if (!l) continue;
            l.ch = pickChar();
            l.target = pickColor();
            l.p = 0;
          }
        }

        for (var j = 0; j < letters.length; j++) {
          var m = letters[j];
          if (m.p < 1) {
            m.p = Math.min(1, m.p + 0.05);
            m.c[0] += (m.target[0] - m.c[0]) * m.p;
            m.c[1] += (m.target[1] - m.c[1]) * m.p;
            m.c[2] += (m.target[2] - m.c[2]) * m.p;
          }
        }

        draw();
        raf = requestAnimationFrame(loop);
      }

      samplePalette();
      build();

      if (reduced) {
        draw(); // 静态一帧：保留纹理，不动
      } else {
        raf = requestAnimationFrame(loop);
        // 页面切到后台就停，别在别的标签页白烧 CPU
        document.addEventListener('visibilitychange', function () {
          if (document.hidden) {
            if (raf) cancelAnimationFrame(raf);
            raf = null;
          } else if (raf === null) {
            last = 0;
            raf = requestAnimationFrame(loop);
          }
        });
      }

      if ('ResizeObserver' in window) {
        new ResizeObserver(function () {
          build();
          if (reduced) draw();
        }).observe(host);
      }

      new MutationObserver(function () {
        samplePalette();
        build();
        if (reduced) draw();
      }).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme']
      });
    });
  }

  /* ============================================================
     AnimatedContent / AnimatedList — 进入视口时复位
     原版用 ScrollTrigger / motion-v useInView；IntersectionObserver 等价。
     ============================================================ */
  var revealObserver = null;

  /* 隐藏态由 JS 加 .vb-armed 才生效（见 vue-bits.css 里的说明）：
     IntersectionObserver 注册在 display:none 的元素上只回调一次 false，
     之后 Alpine 打开 x-show 时不会再回调，元素会永久停在 opacity:0。
     所以只给「当前已参与布局」的元素上锁，其余保持可见，等它进入布局后再处理。 */
  function isLaidOut(el) {
    return el.getClientRects().length > 0;
  }

  function armReveal(el) {
    if (!isLaidOut(el)) return false;

    var stagger = parseFloat(el.dataset.vbRevealStagger || '0');
    if (stagger) {
      var sibs = el.parentNode ? el.parentNode.children : [];
      var idx = Array.prototype.indexOf.call(sibs, el);
      el.style.setProperty('--vb-reveal-delay', Math.min(idx, 8) * stagger + 's');
    }

    el.classList.add('vb-armed');
    revealObserver.observe(el);
    return true;
  }

  function bindReveal() {
    if (reduced) return; // 默认就是可见的，什么都不用做

    if (!revealObserver) {
      revealObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('vb-in');
            revealObserver.unobserve(entry.target); // 一次性，别来回抖
          });
        },
        { threshold: 0.12 }
      );
    }

    var deferred = [];

    each('[data-vb-reveal]', function (el) {
      if (!claim(el, 'Reveal')) return;
      if (!armReveal(el)) deferred.push(el);
    });

    /* 藏在 x-show 里的元素等 Alpine 打开后再上锁。只盯这一批，
       且成功一个就摘一个，列表清空即断开 observer。 */
    if (deferred.length) watchDeferredReveal(deferred);
  }

  var deferredReveals = [];
  var deferredMo = null;

  function watchDeferredReveal(list) {
    list.forEach(function (el) {
      if (deferredReveals.indexOf(el) === -1) deferredReveals.push(el);
    });

    if (deferredMo) return;

    deferredMo = new MutationObserver(function () {
      deferredReveals = deferredReveals.filter(function (el) {
        if (!el.isConnected) return false;
        return !armReveal(el);
      });
      if (!deferredReveals.length) {
        deferredMo.disconnect();
        deferredMo = null;
      }
    });

    // Alpine 的 x-show 改的是 inline style，所以要盯 style 属性
    deferredMo.observe(document.body, {
      attributes: true,
      attributeFilter: ['style', 'class'],
      subtree: true
    });
  }

  /* ============================================================
     GradualBlur — Animations/GradualBlur.vue
     6 层递增 blur，每层 mask 只露自己那一段，叠出渐进模糊。
     ============================================================ */
  function mountGradualBlur() {
    each('[data-vb-gradual-blur]', function (host) {
      if (!claim(host, 'GradBlur')) return;

      var layers = 6;
      var maxBlur = parseFloat(host.dataset.vbGradualBlur || '4');
      var wrap = document.createElement('div');
      wrap.className = 'vb-gradual-blur';
      if (host.dataset.vbGradualBlurHeight) {
        wrap.style.height = host.dataset.vbGradualBlurHeight;
      }

      for (var i = 1; i <= layers; i++) {
        var seg = document.createElement('div');
        var from = ((i - 1) / layers) * 100;
        var to = (i / layers) * 100;
        // 每层 blur 按 2^n 递增，视觉上才是"渐进"而不是均匀分段
        seg.style.setProperty('--vb-blur', (maxBlur * Math.pow(2, i - 1)) / 32 + 'px');
        seg.style.setProperty('--vb-from', from + '%');
        seg.style.setProperty('--vb-to', to + '%');
        wrap.appendChild(seg);
      }
      host.appendChild(wrap);
    });
  }

  /* ============================================================
     DecryptedText — TextAnimations/DecryptedText.vue
     hover 时打乱，逐字归位。sequential + revealDirection=start。
     ============================================================ */
  var DECRYPT_CHARS =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!@#$%^&*()_+'.split('');

  function bindDecrypt() {
    if (reduced) return;

    each('[data-vb-decrypt]', function (el) {
      if (!claim(el, 'Decrypt')) return;

      var text = (el.textContent || '').trim();
      if (!text || text.length > 28) return; // 长文本拆了没意义还伤性能
      var speed = parseFloat(el.dataset.vbDecryptSpeed || '38');
      var timer = null;

      function render(revealed) {
        var html = '';
        for (var i = 0; i < text.length; i++) {
          if (text[i] === ' ') {
            html += ' ';
          } else if (i < revealed) {
            html += escapeHtml(text[i]);
          } else {
            html +=
              '<span class="vb-decrypt-scrambled">' +
              escapeHtml(DECRYPT_CHARS[(Math.random() * DECRYPT_CHARS.length) | 0]) +
              '</span>';
          }
        }
        el.innerHTML = html;
      }

      el.addEventListener('mouseenter', function () {
        if (timer) return;
        var revealed = 0;
        timer = setInterval(function () {
          revealed++;
          if (revealed > text.length) {
            clearInterval(timer);
            timer = null;
            el.textContent = text;
            return;
          }
          render(revealed);
        }, speed);
      });

      el.addEventListener('mouseleave', function () {
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
        el.textContent = text;
      });
    });
  }

  /* textContent 转义后再进 innerHTML。这里的内容全来自页面自身文本，
     但走一道转义免得将来有人把用户数据挂到 data-vb-decrypt 上。 */
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ============================================================
     Counter — Components/Counter.vue
     原版是数字滚轮（每位一列上下滚）。这里做等价的计数补间：
     滚轮那套在 Django 模板里要为每位生成 DOM，代价大于收益。
     ============================================================ */
  function bindCounters() {
    if (reduced || !hasGsap) return;

    each('[data-vb-counter]', function (el) {
      if (!claim(el, 'Counter')) return;

      var raw = (el.textContent || '').trim();
      var target = parseFloat(raw.replace(/,/g, ''));
      if (!isFinite(target)) return;

      var isInt = raw.indexOf('.') === -1;
      var suffix = raw.replace(/^[\d.,\s-]+/, ''); // 保住 "12 个" / "80%" 里的单位
      var obj = { v: 0 };

      el.classList.add('vb-counter');
      window.gsap.to(obj, {
        v: target,
        duration: 1.2,
        ease: 'power2.out',
        onUpdate: function () {
          el.textContent = (isInt ? Math.round(obj.v) : obj.v.toFixed(1)) + suffix;
        }
      });
    });
  }

  /* ============================================================
     挂载
     ============================================================ */
  function init() {
    mountBento();
    bindBentoParticles();
    bindSpotlightCards();
    bindGlare();
    bindMagnets();
    bindClickSpark();
    mountDotGrids();
    mountLetterGlitch();
    bindReveal();
    mountGradualBlur();
    bindDecrypt();
    bindCounters();
  }

  /* Alpine 异步渲染完新内容后调一次，把新节点补挂上（claim 保证不重复绑） */
  function refresh() {
    bindBentoParticles();
    bindGlare();
    bindReveal();
    bindDecrypt();
    bindCounters();
    mountGradualBlur();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.vueBits = { refresh: refresh };
})();
