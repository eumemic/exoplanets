/* Shared page shell: side index with scroll-spy, the starfield (the candidate host stars at their
 * sky positions), scroll reveal, a tooltip, and a canvas helper that handles devicePixelRatio,
 * resizing, reduced motion and pausing while offscreen. No dependencies. */
(function () {
  'use strict';
  var X = window.Exo;
  var reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var TAU = Math.PI * 2;
  var Sky = window.Sky = { reduced: reduced, TAU: TAU };

  /* ---------- side index ---------- */
  function buildIndex() {
    var aside = document.querySelector('aside.index');
    if (!aside) return;
    var secs = Array.prototype.slice.call(document.querySelectorAll('[data-idx]'));
    var pages = [
      ['index.html', 'Infographic abstract'], ['candidates.html', 'Candidate explorer'],
      ['transits.html', 'Transit planner'], ['methods.html', 'Methods and validation']
    ];
    var here = location.pathname.split('/').pop() || 'index.html';
    var h = '<div class="inner"><button type="button" class="index-toggle" aria-expanded="false" aria-controls="index-body"><span>Index</span><span class="cur"></span></button>' +
      '<div class="body" id="index-body"><h2>' + X.esc(aside.getAttribute('data-title') || 'On this page') + '</h2><ol>';
    secs.forEach(function (s) {
      h += '<li><a href="#' + s.id + '"><span class="n">' + X.esc(s.getAttribute('data-idx')) + '</span><span>' + X.esc(s.getAttribute('data-short')) + '</span></a></li>';
    });
    h += '</ol><div class="sub"><h2>Pages</h2>';
    pages.forEach(function (p) { h += '<a href="' + p[0] + '"' + (p[0] === here ? ' aria-current="page"' : '') + '>' + p[1] + '</a>'; });
    h += '<a href="' + X.GH.repo + '">Repository on GitHub</a></div></div></div>';
    aside.innerHTML = h;
    var btn = aside.querySelector('.index-toggle'), body = aside.querySelector('.body'), cur = aside.querySelector('.cur');
    var mq = matchMedia('(max-width: 1040px)');
    function sync() {
      var open = btn.getAttribute('aria-expanded') === 'true';
      body.hidden = mq.matches && !open;
    }
    btn.addEventListener('click', function () { btn.setAttribute('aria-expanded', String(btn.getAttribute('aria-expanded') !== 'true')); sync(); });
    body.addEventListener('click', function (e) { if (e.target.closest('a') && mq.matches) { btn.setAttribute('aria-expanded', 'false'); sync(); } });
    if (mq.addEventListener) mq.addEventListener('change', sync); else mq.addListener(sync);
    sync();
    // scroll-spy: the section whose top has most recently passed a line near the top of the viewport
    var links = aside.querySelectorAll('ol a');
    function spy() {
      var line = 140, idx = 0;
      for (var i = 0; i < secs.length; i++) if (secs[i].getBoundingClientRect().top < line) idx = i;
      for (var j = 0; j < links.length; j++) links[j].classList.toggle('on', j === idx);
      if (secs[idx]) cur.textContent = secs[idx].getAttribute('data-idx') + '  ' + secs[idx].getAttribute('data-short');
    }
    var ticking = false;
    addEventListener('scroll', function () { if (!ticking) { ticking = true; requestAnimationFrame(function () { ticking = false; spy(); }); } }, { passive: true });
    addEventListener('resize', spy);
    spy();
  }

  /* ---------- starfield: registered candidate hosts, equirectangular, RA increasing to the left ---------- */
  var hosts = null;
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967296; }
  function drawStars() {
    var cv = document.getElementById('starfield');
    if (!cv || !hosts) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2), W = innerWidth, H = innerHeight;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    var c = cv.getContext('2d');
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    // the sky spans the larger dimension so stars are not squashed on tall phones
    var S = Math.max(W, H * 1.6), ox = (W - S) / 2, oy = (H - S / 2) / 2;
    hosts.forEach(function (s) {
      var x = ox + ((360 - s.ra) % 360) / 360 * S, y = oy + (90 - s.dec) / 180 * (S / 2);
      if (x < -4 || x > W + 4 || y < -4 || y > H + 4) return;
      var m = isNaN(s.t) ? 12 : s.t;
      var r = Math.max(0.45, 1.75 - (m - 7.5) * 0.2), a = Math.max(0.22, Math.min(0.85, 1.05 - (m - 7.5) * 0.11));
      var warm = hash(s.id);
      var col = warm < 0.55 ? '255,236,206' : (warm < 0.85 ? '236,240,255' : '255,214,160');
      if (r > 1.25) {
        var g = c.createRadialGradient(x, y, 0, x, y, r * 5);
        g.addColorStop(0, 'rgba(' + col + ',' + (a * 0.28) + ')'); g.addColorStop(1, 'rgba(' + col + ',0)');
        c.fillStyle = g; c.beginPath(); c.arc(x, y, r * 5, 0, TAU); c.fill();
      }
      c.fillStyle = 'rgba(' + col + ',' + a + ')';
      c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
    });
  }
  function starfield() {
    var cv = document.createElement('canvas');
    cv.id = 'starfield'; cv.setAttribute('aria-hidden', 'true');
    document.body.insertBefore(cv, document.body.firstChild);
    X.fetchText(X.DATA.ephem.site).then(function (t) {
      hosts = X.parseCSVObjects(t).map(function (r) { return { id: r.TIC, ra: X.num(r.ra), dec: X.num(r.dec), t: X.num(r.Tmag) }; })
        .filter(function (s) { return !isNaN(s.ra) && !isNaN(s.dec); });
      drawStars();
      var tm; addEventListener('resize', function () { clearTimeout(tm); tm = setTimeout(drawStars, 120); });
    }).catch(function () { /* decorative */ });
  }

  /* ---------- reveal on scroll ---------- */
  var revealFns = [];
  function reveal() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window) || reduced) {
      Array.prototype.forEach.call(els, function (e) { e.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { var t = e.target; t.classList.add('in'); io.unobserve(t); setTimeout(function () { t.classList.add('done'); }, 1100); } });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
    Array.prototype.forEach.call(els, function (e) {
      // anything already on screen at load is shown at once; only later panels fade in
      if (e.getBoundingClientRect().top < innerHeight) e.classList.add('in', 'done');
      else io.observe(e);
    });
  }
  /* Run fn once when el first comes into view (immediately under reduced motion). */
  Sky.onView = function (el, fn, margin) {
    if (!el) return;
    if (!('IntersectionObserver' in window)) { fn(); return; }
    var io = new IntersectionObserver(function (es) {
      if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); fn(); }
    }, { rootMargin: margin || '0px 0px -10% 0px' });
    io.observe(el);
  };

  /* ---------- canvas helper ---------- */
  Sky.canvas = function (canvas, draw, opt) {
    opt = opt || {};
    var ctx = canvas.getContext('2d');
    var o = { W: 300, H: 200, dpr: 1, t: opt.t0 || 0, visible: true, ctx: ctx, canvas: canvas };
    function size() {
      var w = Math.max(240, canvas.parentElement.clientWidth);
      var a = typeof opt.aspect === 'function' ? opt.aspect(w) : (opt.aspect || 0.5);
      var h = Math.round(w * a);
      o.dpr = Math.min(window.devicePixelRatio || 1, 2); o.W = w; o.H = h;
      canvas.style.height = h + 'px';
      canvas.width = Math.round(w * o.dpr); canvas.height = Math.round(h * o.dpr);
    }
    var raf = 0, last = 0;
    var animate = opt.animate !== false && !reduced;
    function paint(dt) {
      ctx.setTransform(o.dpr, 0, 0, o.dpr, 0, 0);
      try { draw(ctx, o.W, o.H, o.t, dt || 0); } catch (err) { console.error(err); }
    }
    o.redraw = function () { paint(0); };
    function active() { return !document.hidden && o.visible; }
    function schedule() {
      if (!animate) return;
      if (!active()) { if (raf) cancelAnimationFrame(raf); raf = 0; return; }
      if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
    }
    function frame(now) {
      raf = 0;
      if (!active()) return;
      var dt = Math.min(0.05, (now - last) / 1000); last = now;
      o.t += dt; paint(dt);
      raf = requestAnimationFrame(frame);
    }
    size();
    if (reduced && opt.staticT != null) o.t = opt.staticT;
    paint(0); // first paint always happens, even offscreen, so no canvas is ever blank
    var rt;
    addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { var w = o.W; size(); if (w !== o.W || true) paint(0); }, 80);
    });
    document.addEventListener('visibilitychange', schedule);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { o.visible = es[0].isIntersecting; schedule(); }).observe(canvas);
    }
    schedule();
    return o;
  };

  /* ---------- tooltip ---------- */
  var tip;
  Sky.tip = function (html, x, y) {
    if (!tip) { tip = document.createElement('div'); tip.id = 'tip'; tip.setAttribute('role', 'status'); document.body.appendChild(tip); }
    if (html == null) { tip.style.display = 'none'; return; }
    tip.innerHTML = html; tip.style.display = 'block';
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = x + 14, top = y + 16;
    if (left + w > innerWidth - 8) left = x - w - 14;
    if (top + h > innerHeight - 8) top = y - h - 12;
    tip.style.left = Math.max(8, left) + 'px'; tip.style.top = Math.max(8, top) + 'px';
  };

  /* ---------- small helpers ---------- */
  Sky.n = function (x) { return Number(x).toLocaleString('en-US'); };
  Sky.pct = function (a, b) { return Math.round(100 * a / b); };
  Sky.ease = function (t) { return t <= 0 ? 0 : t >= 1 ? 1 : 1 - Math.pow(1 - t, 3); };
  /* Draw a tier marker (shape and colour) at x, y. */
  Sky.marker = function (c, tier, x, y, r, alpha) {
    var st = X.TIER_STYLE[tier];
    c.globalAlpha = alpha == null ? 1 : alpha;
    c.fillStyle = st ? st.color : '#8e97ab';
    c.beginPath();
    var shape = st ? st.shape : 'circle';
    if (shape === 'circle') c.arc(x, y, r, 0, TAU);
    else if (shape === 'square') c.rect(x - r * 0.88, y - r * 0.88, r * 1.76, r * 1.76);
    else if (shape === 'triangle') { c.moveTo(x, y - r * 1.15); c.lineTo(x + r * 1.05, y + r * 0.8); c.lineTo(x - r * 1.05, y + r * 0.8); c.closePath(); }
    else { c.moveTo(x, y - r * 1.2); c.lineTo(x + r * 1.05, y); c.lineTo(x, y + r * 1.2); c.lineTo(x - r * 1.05, y); c.closePath(); }
    c.fill();
    c.globalAlpha = 1;
  };
  /* After a CSS transition should have finished, pin the final state (frames can be throttled). */
  Sky.settle = function (el, ms) { setTimeout(function () { el.style.transition = 'none'; }, ms); };
  /* Animate a number from 0 to its value once it is in view. */
  Sky.countUp = function (el, value, fmt) {
    fmt = fmt || Sky.n;
    if (reduced) { el.textContent = fmt(value); return; }
    var t0 = 0, dur = 1300, done = false;
    function step(now) {
      if (done) return;
      if (!t0) t0 = now;
      var k = Sky.ease((now - t0) / dur);
      el.textContent = fmt(Math.round(value * k));
      if (k < 1) requestAnimationFrame(step); else done = true;
    }
    requestAnimationFrame(step);
    setTimeout(function () { done = true; el.textContent = fmt(value); }, dur + 400);
  };

  function start() {
    starfield();
    buildIndex();
    reveal();
    X.fillBuildInfo();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
