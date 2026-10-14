/* Landing page: the infographic abstract. Every count is computed from the repository's CSV files
 * at load time; quoted README numbers are in the HTML and tagged as quoted. */
(function () {
  'use strict';
  var X = window.Exo, S = window.Sky, TAU = Math.PI * 2;
  var $ = function (id) { return document.getElementById(id); };
  var COUNTED = ['A', 'B', 'N', 'L1'];
  var C = { ink: '#f4ede1', ink2: '#d3ccbe', dim: '#939cb0', amber: '#f0b25a', amberHi: '#ffd9a0', cool: '#8ec5e6', rose: '#ec95a4', grid: 'rgba(164,182,222,0.12)', grid2: 'rgba(164,182,222,0.24)', well: '#060912' };
  var MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
  var SERIF = '"Iowan Old Style", Charter, Georgia, serif';
  function font(px) { return px + 'px ' + MONO; }
  /* Run an intro from 0 to 1 over dur ms, calling draw(k). A timer guarantees the final state even
   * when animation frames are throttled (background tabs, headless capture). */
  function intro(dur, draw) {
    if (S.reduced) { draw(1); return; }
    var t0 = 0, done = false;
    function step(now) { if (done) return; if (!t0) t0 = now; var k = Math.min(1, (now - t0) / dur); draw(k); if (k < 1) requestAnimationFrame(step); else done = true; }
    requestAnimationFrame(step);
    setTimeout(function () { if (!done) { done = true; draw(1); } }, dur + 400);
  }
  function setLive(key, text) {
    document.querySelectorAll('[data-live="' + key + '"]').forEach(function (el) { el.textContent = text; });
  }
  function rng(seed) { var s = seed >>> 0; return function () { s = (s + 0x6D2B79F5) >>> 0; var t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function gauss(r) { var u = 1 - r(), v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v); }

  /* The spotlight candidate: the values below are only the first-paint defaults and are replaced by
   * the values in the CSV files as soon as they load. */
  var T = { tic: '354944123', P: 18.9082044, Rp: 2.21, depth: 1142, T14: 2.46, b: 0.747 };

  /* ================= 00: stacking sectors (illustration) ================= */
  (function stack() {
    var cv = $('cv-stack'); if (!cv) return;
    var NS = 12, SNR1 = 3, HALF = 5, PER = 90;           // sectors, per-sector SNR, hours shown, points per sector
    var nIn = 2 * T.T14 * PER / (2 * HALF);              // in-transit points per sector
    var sigma = T.depth * Math.sqrt(nIn) / SNR1;
    var r = rng(4342), pts = [];
    for (var s = 0; s < NS; s++) {
      var row = [];
      for (var i = 0; i < PER; i++) {
        var x = -HALF + r() * 2 * HALF;
        row.push([x, model(x) + sigma * gauss(r)]);
      }
      pts.push(row);
    }
    function model(x) {
      var h = T.T14 / 2, ing = 0.28;
      var a = Math.abs(x);
      if (a >= h) return 0;
      if (a > h - ing) return -T.depth * (h - a) / ing;
      return -T.depth;
    }
    var CYCLE = NS * 0.75 + 4.5;
    S.canvas(cv, function (c, W, H, t) {
      var tt = S.reduced ? 1e9 : t % CYCLE;
      var shown = Math.min(NS, 1 + Math.floor(tt / 0.75));
      var fadeOut = (!S.reduced && tt > CYCLE - 0.6) ? (CYCLE - tt) / 0.6 : 1;
      var m = { l: W < 520 ? 12 : 18, r: W < 520 ? 12 : 18, t: 38, b: 34 };
      var pw = W - m.l - m.r, ph = H - m.t - m.b;
      var yr = [-4400, 3000];
      function sx(x) { return m.l + (x + HALF) / (2 * HALF) * pw; }
      function sy(y) { return m.t + (yr[1] - y) / (yr[1] - yr[0]) * ph; }
      c.clearRect(0, 0, W, H);
      // grid
      c.strokeStyle = C.grid; c.lineWidth = 1;
      c.beginPath(); c.moveTo(m.l, sy(0) + 0.5); c.lineTo(W - m.r, sy(0) + 0.5); c.stroke();
      c.setLineDash([2, 4]); c.beginPath(); c.moveTo(m.l, sy(-T.depth) + 0.5); c.lineTo(W - m.r, sy(-T.depth) + 0.5); c.stroke(); c.setLineDash([]);
      // transit window
      c.fillStyle = 'rgba(240,178,90,0.05)';
      c.fillRect(sx(-T.T14 / 2), m.t, sx(T.T14 / 2) - sx(-T.T14 / 2), ph);
      // points
      for (var s = 0; s < shown; s++) {
        var age = Math.min(1, (tt - s * 0.75) / 0.6);
        var newest = s === shown - 1 && shown < NS;
        c.fillStyle = newest ? 'rgba(142,197,230,' + (0.75 * age * fadeOut) + ')' : 'rgba(142,197,230,' + (0.26 * fadeOut) + ')';
        pts[s].forEach(function (p) {
          var y = Math.max(yr[0], Math.min(yr[1], p[1]));
          c.fillRect(sx(p[0]) - 1, sy(y) - 1, 2, 2);
        });
      }
      // binned curve of everything shown so far
      var NB = 30, bw = 2 * HALF / NB, sum = new Array(NB).fill(0), cnt = new Array(NB).fill(0);
      for (s = 0; s < shown; s++) pts[s].forEach(function (p) { var k = Math.min(NB - 1, Math.floor((p[0] + HALF) / bw)); sum[k] += p[1]; cnt[k]++; });
      c.strokeStyle = 'rgba(255,217,160,' + (0.95 * fadeOut) + ')'; c.lineWidth = 2; c.lineJoin = 'round';
      c.shadowColor = 'rgba(240,178,90,0.6)'; c.shadowBlur = 8;
      c.beginPath();
      for (var k = 0; k < NB; k++) {
        var y = cnt[k] ? sum[k] / cnt[k] : 0;
        var X0 = sx(-HALF + (k + 0.5) * bw), Y0 = sy(Math.max(yr[0], y));
        if (k) c.lineTo(X0, Y0); else c.moveTo(X0, Y0);
      }
      c.stroke(); c.shadowBlur = 0;
      // labels
      var snr = SNR1 * Math.sqrt(shown), narrowS = W < 520;
      c.font = font(10.5); c.fillStyle = C.dim; c.textAlign = 'left';
      c.fillText(narrowS ? 'HOURS FROM MID-TRANSIT, \u00B15 H' : 'HOURS FROM MID-TRANSIT, \u00B15 H', m.l, H - 12);
      if (!narrowS) { c.textAlign = 'right'; c.fillText('AMBER: BINNED  \u00B7  BLUE: SIMULATED POINTS', W - m.r, H - 12); }
      c.textAlign = 'left'; c.fillStyle = C.ink2; c.font = font(11);
      c.fillText((narrowS ? 'SECTORS ' : 'ILLUSTRATION  \u00B7  SECTORS COMBINED  ') + shown + ' / ' + NS, m.l, 15);
      c.textAlign = 'right'; c.fillStyle = snr >= 7.1 ? C.amberHi : C.cool;
      c.fillText('SNR \u2248 ' + snr.toFixed(1) + (narrowS ? '' : (snr >= 7.1 ? '  \u00B7  above 7.1' : '  \u00B7  below 7.1')), W - m.r, 15);
      var tw = Math.min(16, (pw * 0.5) / NS);
      for (s = 0; s < NS; s++) {
        c.fillStyle = s < shown ? (snr >= 7.1 ? C.amber : C.cool) : 'rgba(164,182,222,0.18)';
        c.fillRect(m.l + s * (tw + 3), 22, tw, 3);
      }
    }, { aspect: function (w) { return w < 560 ? 0.62 : 0.34; }, staticT: 1e9, t0: NS * 0.75 + 0.2 });
  })();

  /* ================= 01: how a transit works ================= */
  var transitCanvas = (function transit() {
    var cv = $('cv-transit'); if (!cv) return null;
    var u1 = 0.5, u2 = 0.2, Ibar = 1 - u1 / 3 - u2 / 6;
    function I(r) { if (r >= 1) return 0; var mu = Math.sqrt(1 - r * r); return 1 - u1 * (1 - mu) - u2 * (1 - mu) * (1 - mu); }
    function overlap(k, d) { // area of a circle of radius k at distance d from the centre of the unit circle, inside it
      if (d >= 1 + k) return 0;
      if (d <= 1 - k) return Math.PI * k * k;
      var k2 = k * k, d2 = d * d;
      var a1 = k2 * Math.acos((d2 + k2 - 1) / (2 * d * k)), a2 = Math.acos((d2 + 1 - k2) / (2 * d));
      return a1 + a2 - 0.5 * Math.sqrt(Math.max(0, (-d + k + 1) * (d + k - 1) * (d - k + 1) * (d + k + 1)));
    }
    function dip(x, k, b) { var d = Math.sqrt(x * x + b * b); return overlap(k, d) / Math.PI * I(Math.min(d, 0.999)) / Ibar; }
    var CYC = 7.5;
    var o = S.canvas(cv, function (c, W, H, t) {
      var k = Math.sqrt(T.depth / 1e6), b = T.b;
      var L = Math.sqrt((1 + k) * (1 + k) - b * b), v = 2 * L / T.T14;    // stellar radii per hour
      var XR = 1.32, TH = XR / v;                                          // half-range in R* and hours
      var tt = S.reduced ? CYC * 0.47 : t % CYC, p = Math.min(1, tt / (CYC - 1));
      var hour = -TH + p * 2 * TH, xp = hour * v;
      var narrow = W < 560;
      var sceneH = Math.round(H * (narrow ? 0.5 : 0.56));
      var Rs = Math.min(sceneH * 0.4, W * 0.22), cx = W / 2, cy = sceneH / 2 + 8;
      c.clearRect(0, 0, W, H);
      // corona
      var g = c.createRadialGradient(cx, cy, Rs * 0.9, cx, cy, Rs * 1.9);
      g.addColorStop(0, 'rgba(255,170,90,0.16)'); g.addColorStop(1, 'rgba(255,170,90,0)');
      c.fillStyle = g; c.beginPath(); c.arc(cx, cy, Rs * 1.9, 0, TAU); c.fill();
      // limb-darkened disc
      var gd = c.createRadialGradient(cx, cy, 0, cx, cy, Rs);
      for (var i = 0; i <= 12; i++) {
        var r = i / 12, f = I(Math.min(r, 0.999));
        gd.addColorStop(r, 'rgb(' + Math.round(255 * Math.min(1, 0.35 + 0.68 * f)) + ',' + Math.round(222 * f + 18) + ',' + Math.round(170 * f * f + 30) + ')');
      }
      c.fillStyle = gd; c.beginPath(); c.arc(cx, cy, Rs, 0, TAU); c.fill();
      // path of the planet
      var py = cy + b * Rs;
      c.strokeStyle = 'rgba(244,237,225,0.18)'; c.setLineDash([3, 5]); c.lineWidth = 1;
      c.beginPath(); c.moveTo(cx - XR * Rs, py); c.lineTo(cx + XR * Rs, py); c.stroke(); c.setLineDash([]);
      // planet, to scale
      var px = cx + xp * Rs, pr = Math.max(1.6, k * Rs);
      c.fillStyle = '#05070d'; c.beginPath(); c.arc(px, py, pr, 0, TAU); c.fill();
      c.strokeStyle = 'rgba(142,197,230,0.95)'; c.lineWidth = 1; c.beginPath(); c.arc(px, py, pr + 0.6, 0, TAU); c.stroke();
      // label the planet
      c.font = font(10.5); c.fillStyle = C.ink2; c.textAlign = 'left';
      var lx = px + 10, ly = py + 26;
      c.strokeStyle = 'rgba(244,237,225,0.35)'; c.beginPath(); c.moveTo(px + 3, py + 4); c.lineTo(lx - 2, ly - 9); c.stroke();
      c.fillText(T.Rp.toFixed(2) + ' R⊕ planet', lx, ly);
      // light curve
      var m = { l: narrow ? 46 : 64, r: 16, t: sceneH + 22, b: 34 };
      var pw = W - m.l - m.r, ph = H - m.t - m.b;
      var dmax = T.depth * 1.28;
      function sx(h) { return m.l + (h + TH) / (2 * TH) * pw; }
      function sy(f) { return m.t + (f + 0.18 * dmax) / (1.18 * dmax) * ph; } // f in ppm below baseline (positive = dimmer)
      c.strokeStyle = C.grid; c.lineWidth = 1;
      c.beginPath(); c.moveTo(m.l, sy(0) + 0.5); c.lineTo(W - m.r, sy(0) + 0.5); c.stroke();
      c.setLineDash([3, 4]); c.strokeStyle = 'rgba(240,178,90,0.45)';
      c.beginPath(); c.moveTo(m.l, sy(T.depth) + 0.5); c.lineTo(W - m.r, sy(T.depth) + 0.5); c.stroke(); c.setLineDash([]);
      c.font = font(10); c.fillStyle = C.dim; c.textAlign = 'right';
      c.fillText('0', m.l - 8, sy(0) + 3);
      c.fillText('−' + Math.round(T.depth), m.l - 8, sy(T.depth) + 3);
      c.textAlign = 'center';
      for (var h = -Math.floor(TH); h <= Math.floor(TH); h++) {
        c.fillStyle = C.dim; c.fillText((h > 0 ? '+' : '') + h + ' h', sx(h), H - 14);
        c.strokeStyle = C.grid; c.beginPath(); c.moveTo(sx(h) + 0.5, sy(0) + 4); c.lineTo(sx(h) + 0.5, sy(0) + 8); c.stroke();
      }
      c.save(); c.translate(12, m.t + ph / 2); c.rotate(-Math.PI / 2); c.textAlign = 'center'; c.fillText('FLUX (PPM)', 0, 0); c.restore();
      // curve: future faint, past bright
      var N = 220;
      c.lineWidth = 1; c.strokeStyle = 'rgba(240,178,90,0.25)';
      c.beginPath();
      for (i = 0; i <= N; i++) { var hh = -TH + 2 * TH * i / N, yy = sy(1e6 * dip(hh * v, k, b)); if (i) c.lineTo(sx(hh), yy); else c.moveTo(sx(hh), yy); }
      c.stroke();
      c.lineWidth = 2.2; c.strokeStyle = C.amberHi; c.shadowColor = 'rgba(240,178,90,0.7)'; c.shadowBlur = 8;
      c.beginPath();
      var n2 = Math.round(N * p);
      for (i = 0; i <= n2; i++) { hh = -TH + 2 * TH * i / N; yy = sy(1e6 * dip(hh * v, k, b)); if (i) c.lineTo(sx(hh), yy); else c.moveTo(sx(hh), yy); }
      c.stroke(); c.shadowBlur = 0;
      var cyv = sy(1e6 * dip(xp, k, b));
      c.fillStyle = C.amberHi; c.beginPath(); c.arc(sx(hour), cyv, 3.6, 0, TAU); c.fill();
      // depth label
      c.font = font(narrow ? 10 : 11); c.fillStyle = C.amberHi; c.textAlign = 'left';
      var lab = 'depth ≈ (Rp/R*)² = ' + k.toFixed(4) + '² ≈ ' + Math.round(k * k * 1e6) + ' ppm';
      c.fillText(lab, m.l + 4, sy(T.depth) + 16);
      c.fillStyle = C.dim; c.textAlign = 'right';
      c.fillText('b = ' + b.toFixed(2) + '  \u00B7  T14 = ' + T.T14.toFixed(2) + ' h', W - m.r, sy(0) - 8);
    }, { aspect: function (w) { return w < 560 ? 1.05 : 0.6; }, staticT: 0, t0: CYC * 0.4 });
    return o;
  })();
  function transitReadout() {
    var el = $('transit-readout'); if (!el) return;
    el.innerHTML = '<span><b>TIC</b>' + T.tic + '</span><span><b>P</b>' + T.P.toFixed(4) + ' d</span><span><b>R</b>' + T.Rp.toFixed(2) + ' R⊕</span>' +
      '<span><b>T14</b>' + T.T14.toFixed(2) + ' h</span><span><b>depth</b>' + Math.round(T.depth) + ' ppm</span><span><b>b</b>' + T.b.toFixed(2) + '</span>';
  }
  transitReadout();

  /* ================= 07: TOI-4342 orbits (independent of data) ================= */
  (function orbits() {
    var cv = $('cv-orbit'); if (!cv) return;
    var PL = [
      { name: 'b', P: 5.538, col: C.cool, dash: false, ph: 1.1, note: 'confirmed (Tey et al. 2023)' },
      { name: 'c', P: 10.689, col: '#b9d9ee', dash: false, ph: 3.6, note: 'confirmed (Tey et al. 2023)' },
      { name: 'candidate', P: T.P, col: C.amberHi, dash: true, ph: 5.2, note: 'not confirmed' }
    ];
    var DAYS_PER_S = 2.4, WIN = 40;
    S.canvas(cv, function (c, W, H, t) {
      PL[2].P = T.P;
      var day = S.reduced ? 9.3 : t * DAYS_PER_S;
      var narrow = W < 560;
      var stripH = narrow ? 70 : 78, sceneH = H - stripH - 16;
      var cx = W * (narrow ? 0.5 : 0.56), cy = sceneH * (narrow ? 0.62 : 0.58), tilt = narrow ? 0.38 : 0.42;
      var amax = Math.min(W * (narrow ? 0.45 : 0.4), (sceneH * 0.4) / tilt);
      var a3 = Math.pow(PL[2].P, 2 / 3);
      c.clearRect(0, 0, W, H);
      PL.forEach(function (p) { p.a = amax * Math.pow(p.P, 2 / 3) / a3; p.th = p.ph + TAU * day / p.P; });
      function pos(p, th) { return [cx + p.a * Math.cos(th), cy + p.a * Math.sin(th) * tilt]; }
      function orbit(p, front) {
        c.strokeStyle = p.col; c.globalAlpha = front ? 0.75 : 0.32; c.lineWidth = p.dash ? 1.4 : 1.1;
        c.setLineDash(p.dash ? [6, 5] : []);
        c.beginPath(); c.ellipse(cx, cy, p.a, p.a * tilt, 0, front ? 0 : Math.PI, front ? Math.PI : TAU); c.stroke();
        c.setLineDash([]); c.globalAlpha = 1;
      }
      function planet(p) {
        var q = pos(p, p.th), r = p.dash ? 4.2 : 3.6;
        var s = Math.sin(p.th);
        c.fillStyle = p.col; c.beginPath(); c.arc(q[0], q[1], r, 0, TAU); c.fill();
        if (p.dash) { c.strokeStyle = 'rgba(255,217,160,0.5)'; c.beginPath(); c.arc(q[0], q[1], r + 3.5, 0, TAU); c.stroke(); }
        c.font = font(10.5); c.fillStyle = s > 0 ? C.ink : C.dim; c.textAlign = 'left';
        c.fillText(p.name, q[0] + 8, q[1] - 6);
      }
      // line of sight to Earth: towards the viewer, at the bottom of each ellipse
      c.strokeStyle = 'rgba(244,237,225,0.16)'; c.setLineDash([2, 4]);
      c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx, sceneH + 6); c.stroke(); c.setLineDash([]);
      c.font = font(10); c.fillStyle = C.dim; c.textAlign = 'left'; c.fillText('to Earth ↓', cx + 6, sceneH + 2);
      PL.forEach(function (p) { orbit(p, false); });
      PL.forEach(function (p) { if (Math.sin(p.th) <= 0) planet(p); });
      // star, with a brief brightening cue when something transits
      var transiting = PL.filter(function (p) { var d = Math.atan2(Math.sin(p.th - Math.PI / 2), Math.cos(p.th - Math.PI / 2)); return Math.abs(d) < 0.09; });
      var Rst = narrow ? 11 : 14;
      var g = c.createRadialGradient(cx, cy, 0, cx, cy, Rst * 4);
      g.addColorStop(0, 'rgba(255,190,120,0.45)'); g.addColorStop(1, 'rgba(255,190,120,0)');
      c.fillStyle = g; c.beginPath(); c.arc(cx, cy, Rst * 4, 0, TAU); c.fill();
      c.fillStyle = '#ffc98a'; c.beginPath(); c.arc(cx, cy, Rst, 0, TAU); c.fill();
      if (transiting.length) { c.strokeStyle = 'rgba(255,217,160,0.8)'; c.lineWidth = 1.2; c.beginPath(); c.arc(cx, cy, Rst + 5, 0, TAU); c.stroke(); }
      PL.forEach(function (p) { orbit(p, true); });
      PL.forEach(function (p) { if (Math.sin(p.th) > 0) planet(p); });
      // legend
      var lx = 14, ly = 22;
      c.font = font(narrow ? 10 : 11); c.textAlign = 'left';
      PL.forEach(function (p, i) {
        var y = ly + i * 18;
        c.strokeStyle = p.col; c.lineWidth = 1.6; c.setLineDash(p.dash ? [5, 4] : []);
        c.beginPath(); c.moveTo(lx, y - 4); c.lineTo(lx + 20, y - 4); c.stroke(); c.setLineDash([]);
        c.fillStyle = p.dash ? C.amberHi : C.ink2;
        c.fillText(p.name + '  ' + p.P.toFixed(2) + ' d  ' + (narrow ? p.note.replace(' (Tey et al. 2023)', '') : p.note), lx + 28, y);
      });
      c.fillStyle = C.dim; c.fillText('day ' + day.toFixed(1), lx, ly + 3 * 18 + 4);
      // light-curve strip: the last WIN days, one notch per transit
      var y0 = H - stripH + 10, sh = stripH - 30, sl = 14, sr = W - 14;
      c.strokeStyle = C.grid2; c.lineWidth = 1;
      c.font = font(10); c.fillStyle = C.dim; c.textAlign = 'left';
      c.fillText((narrow ? '' : 'ONE LIGHT CURVE, THREE SIGNALS  ·  ') + 'LAST ' + WIN + ' DAYS', sl, y0 - 2);
      var base = y0 + 10;
      c.strokeStyle = 'rgba(244,237,225,0.35)';
      c.beginPath(); c.moveTo(sl, base); c.lineTo(sr, base); c.stroke();
      PL.forEach(function (p) {
        // transits happen when the planet crosses the line of sight (angle pi/2)
        var first = ((Math.PI / 2 - p.ph) % TAU + TAU) % TAU / TAU * p.P;
        for (var n = Math.ceil((day - WIN - first) / p.P); ; n++) {
          var tn = first + n * p.P;
          if (tn > day) break;
          var x = sl + (tn - (day - WIN)) / WIN * (sr - sl);
          c.strokeStyle = p.col; c.lineWidth = 2;
          c.setLineDash(p.dash ? [3, 2] : []);
          c.beginPath(); c.moveTo(x, base); c.lineTo(x, base + sh * 0.85); c.stroke(); c.setLineDash([]);
        }
      });
      c.fillStyle = C.dim; c.textAlign = 'right'; c.fillText('now', sr, base + sh + 6);
    }, { aspect: function (w) { return w < 560 ? 1.3 : 0.56; }, staticT: 0 });
  })();

  /* ================= data-driven panels ================= */
  X.loadCandidates().then(function (rows) {
    var counted = rows.filter(function (r) { return COUNTED.indexOf(r.tier) >= 0; });
    var full = counted.filter(function (r) { return r.search === 'full-sky'; });
    var earlier = counted.filter(function (r) { return r.search === 'earlier'; });
    var stars = new Set(counted.map(function (r) { return r.tic; })).size;
    var medR = X.median(counted.map(function (r) { return r.Rp; }));
    var small = counted.filter(function (r) { return r.Rp < 4; }).length;
    var valid = counted.filter(function (r) { return r.fpp < 0.015 && r.nfpp < 0.001; }).length;
    setLive('counted', S.n(counted.length));
    setLive('counted-split', S.n(full.length) + ' full-sky + ' + S.n(earlier.length) + ' earlier');
    setLive('stars', S.n(stars));
    setLive('medR', X.fmt(medR, 1));
    setLive('small', S.n(small) + ' (' + S.pct(small, counted.length) + '%)');
    setLive('valid', S.n(valid));
    setLive('L1', S.n(counted.filter(function (r) { return r.tier === 'L1'; }).length));
    setLive('eb', S.n(rows.filter(function (r) { return r.search === 'full-sky' && r.tier === 'likely EB'; }).length));

    // spotlight values from the tables
    var spot = counted.filter(function (r) { return r.tic === T.tic && Math.abs(r.P - 18.908) < 0.01; })[0];
    if (spot) {
      T.P = spot.P; T.Rp = spot.Rp;
      if (!isNaN(spot.b)) T.b = spot.b;
      if (!isNaN(spot.depth)) T.depth = spot.depth;
      if (!isNaN(spot.T14)) T.T14 = spot.T14;
      setLive('toiP', T.P.toFixed(4));
      transitReadout();
      if (transitCanvas) transitCanvas.redraw();
    }

    funnel(rows, full, earlier);
    skyMap(counted);
    periodRadius(counted);
  }).catch(function (err) { X.showError($('stats'), err); });

  /* ================= 02: funnel ================= */
  function funnel(rows, full, earlier) {
    var el = $('funnel'); if (!el) return;
    var catalogue = rows.filter(function (r) { return r.search === 'full-sky'; }).length;
    var st = [
      { v: 4039203, l: 'stars searched', q: true },
      { v: 7459491, l: 'signals found', q: true },
      { v: 609021, l: 'pass the pre-filters (SNR ≥ 9, ≥ 3 transits, duration and shape cuts)', q: true },
      { v: 13986, l: 'unmatched to known signals and pass every LEO-Vetter test', q: true },
      { v: catalogue, l: 'signals in the full-sky catalogue, with fits, pixel checks and binary checks' },
      { v: full.length, l: 'counted full-sky candidates (tiers A, B, N, L1)', final: true },
      { v: full.length + earlier.length, l: 'counted in all, with ' + earlier.length + ' from the earlier searches (tiers A, B)', final: true, sum: true }
    ];
    var max = Math.log10(Math.max.apply(null, st.map(function (x) { return x.v; })));
    el.innerHTML = st.map(function (s) {
      return '<li class="' + (s.final ? 'final' : '') + (s.sum ? ' sum' : '') + '"><span class="lab">' + X.esc(s.l) +
        (s.q ? ' <span class="tag t-quoted">quoted</span>' : ' <span class="tag t-live">CSV</span>') + '</span>' +
        '<span class="num" data-v="' + s.v + '">' + S.n(s.v) + '</span><span class="track"><span class="bar" data-w="' + (100 * Math.log10(s.v) / max).toFixed(2) + '"></span></span></li>';
    }).join('');
    S.onView(el, function () {
      el.querySelectorAll('.bar').forEach(function (b, i) { setTimeout(function () { b.style.width = b.getAttribute('data-w') + '%'; S.settle(b, 1900); }, S.reduced ? 0 : i * 140); });
      el.querySelectorAll('.num').forEach(function (n) { S.countUp(n, +n.getAttribute('data-v')); });
    });
  }

  /* ================= 03: sky map ================= */
  function skyMap(counted) {
    var cv = $('cv-sky'); if (!cv) return;
    var pts = counted.filter(function (r) { return !isNaN(r.ra) && !isNaN(r.dec); });
    var D = Math.PI / 180, EPS = 23.4393 * D;
    function hammer(ra, dec) {
      var l = ((ra + 180) % 360 + 360) % 360 - 180; l = -l * D; var p = dec * D;
      var z = Math.sqrt(1 + Math.cos(p) * Math.cos(l / 2));
      return [2 * Math.SQRT2 * Math.cos(p) * Math.sin(l / 2) / z, Math.SQRT2 * Math.sin(p) / z];
    }
    function eclToEq(lam) { var dec = Math.asin(Math.sin(EPS) * Math.sin(lam)); var ra = Math.atan2(Math.cos(EPS) * Math.sin(lam), Math.cos(lam)); return [((ra / D) + 360) % 360, dec / D]; }
    function galToEq(l) {
      var aG = 192.85948 * D, dG = 27.12825 * D, lN = 122.93192 * D;
      var dec = Math.asin(Math.cos(dG) * Math.cos(lN - l));
      var ra = aG + Math.atan2(Math.sin(lN - l), -Math.sin(dG) * Math.cos(lN - l));
      return [((ra / D) % 360 + 360) % 360, dec / D];
    }
    function eclLat(ra, dec) { var a = ra * D, d = dec * D; return Math.asin(Math.sin(d) * Math.cos(EPS) - Math.cos(d) * Math.sin(EPS) * Math.sin(a)) / D; }
    var order = { B: 0, N: 1, L1: 2, A: 3 };
    pts.sort(function (a, b) { return order[a.tier] - order[b.tier]; });
    var rnd = rng(7); pts.forEach(function (p) { p._d = rnd(); });
    var geo = { s: 1, cx: 0, cy: 0 }, hover = null, introK = S.reduced ? 1 : 0;
    function proj(ra, dec) { var h = hammer(ra, dec); return [geo.cx + h[0] * geo.s, geo.cy - h[1] * geo.s]; }
    function curve(c, fn, n, split) {
      var prev = null; c.beginPath();
      for (var i = 0; i <= n; i++) {
        var e = fn(i / n * TAU), q = proj(e[0], e[1]);
        if (prev && Math.abs(q[0] - prev[0]) > geo.s * 1.2) c.moveTo(q[0], q[1]); else if (prev) c.lineTo(q[0], q[1]); else c.moveTo(q[0], q[1]);
        prev = q;
      }
      c.stroke();
    }
    var o = S.canvas(cv, function (c, W, H) {
      var m = W < 560 ? 6 : 18;
      geo.s = Math.min((W - 2 * m) / (4 * Math.SQRT2), (H - 2 * m - 16) / (2 * Math.SQRT2));
      geo.cx = W / 2; geo.cy = H / 2 + 6;
      c.clearRect(0, 0, W, H);
      // sky disc
      var g = c.createRadialGradient(geo.cx, geo.cy, 0, geo.cx, geo.cy, geo.s * 2.9);
      g.addColorStop(0, 'rgba(26,38,72,0.55)'); g.addColorStop(1, 'rgba(10,16,32,0.35)');
      c.fillStyle = g; c.beginPath(); c.ellipse(geo.cx, geo.cy, 2 * Math.SQRT2 * geo.s, Math.SQRT2 * geo.s, 0, 0, TAU); c.fill();
      // graticule
      c.strokeStyle = C.grid; c.lineWidth = 1;
      for (var ra = 0; ra < 360; ra += 30) { c.beginPath(); for (var d = -90; d <= 90; d += 3) { var q = proj(ra === 180 ? 179.999 : ra, d); if (d === -90) c.moveTo(q[0], q[1]); else c.lineTo(q[0], q[1]); } c.stroke(); }
      for (d = -60; d <= 60; d += 30) { c.beginPath(); for (ra = -179.999; ra <= 180; ra += 3) { q = proj(ra, d); if (ra === -179.999) c.moveTo(q[0], q[1]); else c.lineTo(q[0], q[1]); } c.stroke(); }
      c.strokeStyle = C.grid2; c.beginPath(); c.ellipse(geo.cx, geo.cy, 2 * Math.SQRT2 * geo.s, Math.SQRT2 * geo.s, 0, 0, TAU); c.stroke();
      // Galactic plane and ecliptic
      c.lineWidth = Math.max(6, geo.s * 0.12); c.strokeStyle = 'rgba(142,197,230,0.05)'; curve(c, galToEq, 360);
      c.lineWidth = 1; c.strokeStyle = 'rgba(142,197,230,0.32)'; curve(c, galToEq, 360);
      c.setLineDash([5, 5]); c.strokeStyle = 'rgba(240,178,90,0.5)'; curve(c, eclToEq, 360); c.setLineDash([]);
      // labels
      c.font = font(10); c.fillStyle = C.dim; c.textAlign = 'center';
      for (var hr = 0; hr < 24; hr += 4) { if (hr === 12) continue; var qq = proj(hr * 15, 0); c.fillText(hr + 'h', qq[0], qq[1] + 13); }
      [60, 30, -30, -60].forEach(function (dd) { var qd = proj(179.999, dd); c.textAlign = dd > 0 ? 'right' : 'right'; c.fillText((dd > 0 ? '+' : '−') + Math.abs(dd) + '°', qd[0] - 6, qd[1] + 3); });
      if (W >= 560) {
      var qe = proj(eclToEq(200 * D)[0], eclToEq(200 * D)[1]);
      c.fillStyle = 'rgba(240,178,90,0.8)'; c.textAlign = 'left'; c.fillText('ecliptic', qe[0] + 6, qe[1] - 6);
      var qg = proj(galToEq(60 * D)[0], galToEq(60 * D)[1]);
      c.fillStyle = 'rgba(142,197,230,0.8)'; c.fillText('Galactic plane', qg[0] + 8, qg[1] + 4);
      }
      // candidates
      var r = W < 560 ? 1.8 : 2.9;
      pts.forEach(function (p) {
        var a = Math.max(0, Math.min(1, (introK * 1.4 - p._d * 0.9) / 0.5));
        if (a <= 0) return;
        var q = proj(p.ra, p.dec); p._x = q[0]; p._y = q[1];
        S.marker(c, p.tier, q[0], q[1], r, 0.9 * a);
      });
      if (hover) {
        c.strokeStyle = C.ink; c.lineWidth = 1.2; c.beginPath(); c.arc(hover._x, hover._y, r + 5, 0, TAU); c.stroke();
      }
    }, { aspect: function (w) { return w < 560 ? 0.62 : 0.52; }, animate: false });
    // intro sweep, once in view
    S.onView(cv, function () { intro(1600, function (k) { introK = k; o.redraw(); }); });
    // interaction
    function nearest(x, y) {
      var best = null, bd = 12 * 12;
      pts.forEach(function (p) { if (p._x == null) return; var d = (p._x - x) * (p._x - x) + (p._y - y) * (p._y - y); if (d < bd) { bd = d; best = p; } });
      return best;
    }
    function tipHTML(p) {
      return '<div class="h">TIC ' + X.esc(p.tic) + '</div><span class="k">tier</span> ' + X.esc(p.tier) + ' &middot; <span class="k">P</span> ' + X.fmt(p.P, 3) + ' d &middot; <span class="k">R</span> ' + X.fmt(p.Rp, 2) + ' R&oplus;<br>' +
        '<span class="k">RA</span> ' + X.fmt(p.ra, 2) + '&deg; &middot; <span class="k">Dec</span> ' + X.fmt(p.dec, 2) + '&deg;<br><span class="k">select to open in the explorer</span>';
    }
    var lastTap = null;
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      var b = cv.getBoundingClientRect(), p = nearest(e.clientX - b.left, e.clientY - b.top);
      if (p !== hover) { hover = p; o.redraw(); }
      cv.style.cursor = p ? 'pointer' : 'default';
      S.tip(p ? tipHTML(p) : null, e.clientX, e.clientY);
    });
    cv.addEventListener('pointerleave', function () { hover = null; o.redraw(); S.tip(null); });
    cv.addEventListener('click', function (e) {
      var b = cv.getBoundingClientRect(), p = nearest(e.clientX - b.left, e.clientY - b.top);
      if (!p) { S.tip(null); hover = null; o.redraw(); return; }
      if (e.pointerType === 'mouse' || p === lastTap) { location.href = 'candidates.html?q=' + encodeURIComponent(p.tic); return; }
      lastTap = p; hover = p; o.redraw(); S.tip(tipHTML(p).replace('select to open', 'tap again to open'), e.clientX, e.clientY);
    });
    // legend, counts, caption
    var counts = {}; pts.forEach(function (p) { counts[p.tier] = (counts[p.tier] || 0) + 1; });
    $('sky-legend').innerHTML = COUNTED.map(function (t) { return '<span class="tag">' + X.tierDot(t) + 'Tier ' + t + ' &middot; ' + (counts[t] || 0) + '</span>'; }).join('') +
      '<span class="tag"><svg class="tier-dot" viewBox="0 0 12 12" aria-hidden="true"><path d="M0 6 H12" stroke="#f0b25a" stroke-dasharray="3 2"/></svg>ecliptic</span><span class="tag"><svg class="tier-dot" viewBox="0 0 12 12" aria-hidden="true"><path d="M0 6 H12" stroke="#8ec5e6"/></svg>Galactic plane</span>';
    $('sky-count').textContent = S.n(pts.length) + ' plotted';
    var polar = pts.filter(function (p) { return Math.abs(eclLat(p.ra, p.dec)) > 60; }).length;
    var cap = $('sky-cap');
    cap.insertAdjacentHTML('afterbegin', S.n(polar) + ' of ' + S.n(pts.length) + ' (' + S.pct(polar, pts.length) + '%) lie within 30&deg; of an ecliptic pole, where TESS observes longest, in its continuous viewing zones. ');
  }

  /* ================= 04: period-radius plane ================= */
  function periodRadius(counted) {
    var cv = $('cv-pr'); if (!cv) return;
    var pts = counted.filter(function (r) { return r.P > 0 && r.Rp > 0; });
    var show = { A: true, B: true, N: true, L1: true };
    var order = { B: 0, N: 1, L1: 2, A: 3 };
    pts.sort(function (a, b) { return order[a.tier] - order[b.tier]; });
    var xr = [0.4, 70], yr = [0.6, 25], hover = null, introK = S.reduced ? 1 : 0;
    var desert = counted.filter(function (r) { return r.flags.indexOf('Neptunian desert') >= 0; }).length;
    var geo = {};
    var o = S.canvas(cv, function (c, W, H) {
      var narrow = W < 560;
      var m = { l: narrow ? 40 : 52, r: narrow ? 50 : 70, t: 14, b: 42 };
      var pw = W - m.l - m.r, ph = H - m.t - m.b;
      function sx(p) { return m.l + Math.log(p / xr[0]) / Math.log(xr[1] / xr[0]) * pw; }
      function sy(r) { return m.t + ph - Math.log(r / yr[0]) / Math.log(yr[1] / yr[0]) * ph; }
      geo.sx = sx; geo.sy = sy;
      c.clearRect(0, 0, W, H);
      // grid
      c.font = font(10); c.lineWidth = 1;
      [0.5, 1, 2, 3, 5, 10, 20, 30, 50].forEach(function (v) {
        c.strokeStyle = C.grid; c.beginPath(); c.moveTo(sx(v) + 0.5, m.t); c.lineTo(sx(v) + 0.5, m.t + ph); c.stroke();
        c.fillStyle = C.dim; c.textAlign = 'center'; c.fillText(String(v), sx(v), H - m.b + 16);
      });
      [0.7, 1, 1.5, 2, 3, 4, 6, 10, 20].forEach(function (v) {
        c.strokeStyle = C.grid; c.beginPath(); c.moveTo(m.l, sy(v) + 0.5); c.lineTo(m.l + pw, sy(v) + 0.5); c.stroke();
        c.fillStyle = C.dim; c.textAlign = 'right'; c.fillText(String(v), m.l - 7, sy(v) + 3);
      });
      c.fillStyle = C.dim; c.textAlign = 'center'; c.fillText('ORBITAL PERIOD (DAYS)', m.l + pw / 2, H - 8);
      c.save(); c.translate(11, m.t + ph / 2); c.rotate(-Math.PI / 2); c.fillText('RADIUS (R⊕)', 0, 0); c.restore();
      // radius valley band
      c.fillStyle = 'rgba(142,197,230,0.08)'; c.beginPath();
      var N = 40, i, P, Rc;
      for (i = 0; i <= N; i++) { P = xr[0] * Math.pow(xr[1] / xr[0], i / N); Rc = Math.pow(10, -0.09 * Math.log10(P) + 0.37 + 0.045); if (i) c.lineTo(sx(P), sy(Rc)); else c.moveTo(sx(P), sy(Rc)); }
      for (i = N; i >= 0; i--) { P = xr[0] * Math.pow(xr[1] / xr[0], i / N); Rc = Math.pow(10, -0.09 * Math.log10(P) + 0.37 - 0.045); c.lineTo(sx(P), sy(Rc)); }
      c.closePath(); c.fill();
      c.fillStyle = 'rgba(142,197,230,0.85)'; c.textAlign = 'left'; c.font = font(narrow ? 9.5 : 10.5);
      var lp = 0.43; c.fillText('radius valley (approx.)', sx(lp), sy(Math.pow(10, -0.09 * Math.log10(lp) + 0.37 - 0.045)) + 13);
      // Neptunian desert core
      c.fillStyle = 'rgba(236,149,164,0.09)'; c.strokeStyle = 'rgba(236,149,164,0.55)'; c.setLineDash([4, 4]);
      c.fillRect(sx(xr[0]), sy(10), sx(3.2) - sx(xr[0]), sy(4) - sy(10));
      c.strokeRect(sx(xr[0]) + 0.5, sy(10) + 0.5, sx(3.2) - sx(xr[0]), sy(4) - sy(10)); c.setLineDash([]);
      c.fillStyle = C.rose; c.textAlign = 'left';
      c.fillText('Neptunian', sx(xr[0]) + 6, sy(10) + 14); c.fillText('desert core', sx(xr[0]) + 6, sy(10) + 27);
      // reference radii
      [[1, 'Earth'], [3.88, 'Neptune'], [11.2, 'Jupiter']].forEach(function (rf) {
        var y = sy(rf[0]);
        c.strokeStyle = 'rgba(244,237,225,0.4)'; c.beginPath(); c.moveTo(m.l + pw + 2, y + 0.5); c.lineTo(m.l + pw + 8, y + 0.5); c.stroke();
        c.fillStyle = C.ink2; c.textAlign = 'left'; c.fillText(rf[1], m.l + pw + 11, y + 3);
      });
      c.strokeStyle = C.grid2; c.strokeRect(m.l + 0.5, m.t + 0.5, pw, ph);
      // points
      var r = narrow ? 2.6 : 3.2;
      pts.forEach(function (p) {
        p._x = null;
        if (!show[p.tier]) return;
        var a = Math.max(0, Math.min(1, (introK * 1.6 - Math.log(p.P / xr[0]) / Math.log(xr[1] / xr[0]) * 0.6) / 0.4));
        if (a <= 0) return;
        p._x = sx(p.P); p._y = sy(p.Rp);
        S.marker(c, p.tier, p._x, p._y, r * (0.4 + 0.6 * a), 0.88 * a);
      });
      if (hover && hover._x != null) { c.strokeStyle = C.ink; c.lineWidth = 1.2; c.beginPath(); c.arc(hover._x, hover._y, r + 5, 0, TAU); c.stroke(); }
    }, { aspect: function (w) { return w < 560 ? 0.95 : 0.6; }, animate: false });
    S.onView(cv, function () { intro(1500, function (k) { introK = k; o.redraw(); }); });
    function nearest(x, y) {
      var best = null, bd = 12 * 12;
      pts.forEach(function (p) { if (p._x == null) return; var d = (p._x - x) * (p._x - x) + (p._y - y) * (p._y - y); if (d < bd) { bd = d; best = p; } });
      return best;
    }
    function tipHTML(p) {
      return '<div class="h">TIC ' + X.esc(p.tic) + '</div><span class="k">tier</span> ' + X.esc(p.tier) + ' &middot; ' + X.esc(p.search) + '<br><span class="k">P</span> ' + X.fmt(p.P, 4) + ' d &middot; <span class="k">R</span> ' + X.fmt(p.Rp, 2) + ' R&oplus;' +
        (p.flags.length ? '<br><span class="k">' + X.esc(p.flags.join('; ')) + '</span>' : '');
    }
    var lastTap = null;
    cv.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      var b = cv.getBoundingClientRect(), p = nearest(e.clientX - b.left, e.clientY - b.top);
      if (p !== hover) { hover = p; o.redraw(); }
      cv.style.cursor = p ? 'pointer' : 'default';
      S.tip(p ? tipHTML(p) : null, e.clientX, e.clientY);
    });
    cv.addEventListener('pointerleave', function () { hover = null; o.redraw(); S.tip(null); });
    cv.addEventListener('click', function (e) {
      var b = cv.getBoundingClientRect(), p = nearest(e.clientX - b.left, e.clientY - b.top);
      if (!p) { S.tip(null); return; }
      if (e.pointerType === 'mouse' || p === lastTap) { location.href = 'candidates.html?q=' + encodeURIComponent(p.tic); return; }
      lastTap = p; hover = p; o.redraw(); S.tip(tipHTML(p) + '<br><span class="k">tap again to open</span>', e.clientX, e.clientY);
    });
    // tier toggles
    var tg = $('pr-toggles');
    var counts = {}; pts.forEach(function (p) { counts[p.tier] = (counts[p.tier] || 0) + 1; });
    tg.innerHTML = COUNTED.map(function (t) {
      return '<button type="button" class="btn small" aria-pressed="true" data-tier="' + t + '">' + X.tierDot(t) + 'Tier ' + t + ' &middot; ' + (counts[t] || 0) + '</button>';
    }).join('');
    tg.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-tier]'); if (!b) return;
      var t = b.getAttribute('data-tier'); show[t] = !show[t];
      b.setAttribute('aria-pressed', String(show[t])); o.redraw();
      var n = pts.filter(function (p) { return show[p.tier]; }).length;
      $('pr-count').textContent = S.n(n) + ' shown';
    });
    $('pr-count').textContent = S.n(pts.length) + ' shown';
    $('pr-cap').insertAdjacentHTML('afterbegin', S.n(desert) + ' counted full-sky candidates carry the desert flag. ');
  }

  /* ================= 05: findability ================= */
  (function findability() {
    var cv = $('cv-find'); if (!cv) return;
    var steps = [
      { k: 'snr_to_s26', s: 'S26', d: 'Jul 2020' }, { k: 'snr_to_s55', s: 'S55', d: 'Sep 2022' }, { k: 'snr_to_s69', s: 'S69', d: 'Sep 2023' },
      { k: 'snr_to_s83', s: 'S83', d: 'Sep 2024' }, { k: 'snr_to_s96', s: 'S96', d: 'Sep 2025' }, { k: 'snr', s: 'S104', d: 'all sectors' }
    ];
    var vals = null, prog = S.reduced ? 1 : 0, total = 0;
    var o = S.canvas(cv, function (c, W, H) {
      c.clearRect(0, 0, W, H);
      var narrow = W < 480;
      var m = { l: narrow ? 34 : 40, r: 12, t: 54, b: 46 };
      c.font = font(narrow ? 9.5 : 10);
      var pw = W - m.l - m.r, ph = H - m.t - m.b;
      function sx(i) { return m.l + (i + 0.5) / steps.length * pw; }
      function sy(f) { return m.t + ph - f * ph; }
      c.font = font(narrow ? 9.5 : 10); c.lineWidth = 1;
      [0, 0.25, 0.5, 0.75, 1].forEach(function (f) {
        c.strokeStyle = C.grid; c.beginPath(); c.moveTo(m.l, sy(f) + 0.5); c.lineTo(m.l + pw, sy(f) + 0.5); c.stroke();
        c.fillStyle = C.dim; c.textAlign = 'right'; c.fillText(Math.round(f * 100) + '%', m.l - 6, sy(f) + 3);
      });
      // the newest sectors, shaded
      var x96 = (sx(4) + sx(5)) / 2;
      c.fillStyle = 'rgba(142,197,230,0.06)'; c.fillRect(x96, m.t, m.l + pw - x96, ph);
      c.fillStyle = 'rgba(142,197,230,0.75)'; c.textAlign = 'center'; c.fillText('S97–104', (x96 + m.l + pw) / 2, m.t - 30);
      steps.forEach(function (s, i) {
        c.fillStyle = C.ink2; c.textAlign = 'center'; c.fillText(s.s, sx(i), H - m.b + 16);
        c.fillStyle = C.dim; c.fillText(narrow ? (s.d === 'all sectors' ? 'all' : s.d.slice(-4)) : s.d, sx(i), H - m.b + 30);
      });
      if (!vals) return;
      var n = steps.length, upto = prog * (n - 1);
      // area + line up to the current progress
      function ptAt(u) { var i = Math.floor(u), f = u - i; var a = vals[i], b = vals[Math.min(n - 1, i + 1)]; return [sx(i) + (sx(Math.min(n - 1, i + 1)) - sx(i)) * f, sy(a + (b - a) * f)]; }
      var g = c.createLinearGradient(0, m.t, 0, m.t + ph);
      g.addColorStop(0, 'rgba(240,178,90,0.28)'); g.addColorStop(1, 'rgba(240,178,90,0.02)');
      c.fillStyle = g; c.beginPath(); c.moveTo(sx(0), sy(0));
      for (var u = 0; u <= upto + 1e-9; u += 0.02) { var q = ptAt(Math.min(u, upto)); c.lineTo(q[0], q[1]); }
      var qe = ptAt(upto); c.lineTo(qe[0], qe[1]); c.lineTo(qe[0], sy(0)); c.closePath(); c.fill();
      c.strokeStyle = C.amberHi; c.lineWidth = 2.2; c.shadowColor = 'rgba(240,178,90,0.6)'; c.shadowBlur = 8;
      c.beginPath(); c.moveTo(sx(0), sy(vals[0]));
      for (u = 0; u <= upto + 1e-9; u += 0.02) { q = ptAt(Math.min(u, upto)); c.lineTo(q[0], q[1]); }
      c.lineTo(qe[0], qe[1]); c.stroke(); c.shadowBlur = 0;
      for (var i = 0; i < n; i++) {
        if (i > upto + 1e-6) break;
        c.fillStyle = C.well; c.strokeStyle = C.amberHi; c.lineWidth = 1.6;
        c.beginPath(); c.arc(sx(i), sy(vals[i]), 4, 0, TAU); c.fill(); c.stroke();
        c.fillStyle = i === 1 ? C.amberHi : C.ink; c.font = font(i === 1 ? 12 : 11); c.textAlign = 'center';
        c.fillText(Math.round(vals[i] * 100) + '%', sx(i), sy(vals[i]) - 11);
      }
    }, { aspect: function (w) { return w < 480 ? 0.95 : 0.84; }, animate: false });
    X.fetchText(X.DATA.findability.site).then(function (txt) {
      var rows = X.parseCSVObjects(txt);
      total = rows.length;
      // SNR above 9 reproduces the counts in findability.md (one row sits at 9.0 after rounding)
      vals = steps.map(function (s) { return rows.filter(function (r) { return X.num(r[s.k]) > 9; }).length / total; });
      var at96 = rows.filter(function (r) { return X.num(r.snr_to_s96) > 9; }).length;
      var atAll = rows.filter(function (r) { return X.num(r.snr) > 9; }).length;
      var ffi = rows.filter(function (r) { return r.two_min === 'False'; }).length;
      var weak = rows.filter(function (r) { return X.num(r.best_sector_snr) < 7.1; }).length;
      var med = X.median(rows.map(function (r) { return X.num(r.best_sector_snr); }));
      var f = [
        [S.pct(ffi, total) + '%', S.n(ffi) + ' of ' + S.n(total) + ' are on stars observed only in full-frame images in their transit sectors, outside SPOC’s multi-sector searches.', ffi / total],
        [S.pct(weak, total) + '%', 'never reach SNR 7.1, SPOC’s threshold, in any single sector. The median best sector reaches ' + X.fmt(med, 1) + '.', weak / total],
        [S.n(atAll - at96), 'needed Sectors 97–104 to reach SNR 9; ' + S.n(at96) + ' (' + S.pct(at96, total) + '%) were there with data through Sector 96.', (atAll - at96) / total]
      ];
      $('find-facts').innerHTML = f.map(function (x) { return '<div class="fact"><div class="v">' + x[0] + '</div><div class="l">' + x[1] + '</div><div class="meter"><i data-w="' + (100 * x[2]).toFixed(1) + '"></i></div></div>'; }).join('');
      $('find-cap').insertAdjacentHTML('afterbegin', 'Covers the ' + S.n(total) + ' full-sky candidates in tiers A, B and N on 12 October; the counted tiers have changed slightly since. ');
      o.redraw();
      S.onView(cv, function () {
        document.querySelectorAll('#find-facts .meter i').forEach(function (m) { m.style.width = m.getAttribute('data-w') + '%'; S.settle(m, 1900); });
        intro(1800, function (k) { prog = S.ease(k); o.redraw(); });
      });
    }).catch(function (err) { X.showError($('find-facts'), err); });
  })();

  /* ================= 08: next transits ================= */
  (function nextTransits() {
    var list = $('next-list'), cv = $('cv-next'); if (!list || !cv) return;
    var rows = null;
    function utcMs(s) { return Date.parse(s.replace(' ', 'T') + ':00Z'); }
    var o = S.canvas(cv, function (c, W, H) {
      c.clearRect(0, 0, W, H);
      var now = Date.now(), t0 = now - 2 * 3600e3, t1 = now + 46 * 3600e3;
      var m = { l: 12, r: 12, t: 34, b: 26 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
      function sx(t) { return m.l + (t - t0) / (t1 - t0) * pw; }
      var base = m.t + ph;
      c.font = font(10); c.lineWidth = 1;
      // 6-hour grid in UTC
      var g0 = Math.ceil(t0 / (6 * 3600e3)) * 6 * 3600e3;
      for (var g = g0; g < t1; g += 6 * 3600e3) {
        var d = new Date(g);
        c.strokeStyle = C.grid; c.beginPath(); c.moveTo(sx(g) + 0.5, m.t); c.lineTo(sx(g) + 0.5, base); c.stroke();
        c.fillStyle = C.dim; c.textAlign = 'center';
        var lab = d.getUTCHours() === 0 ? d.toISOString().slice(5, 10) : String(d.getUTCHours()).padStart(2, '0') + 'h';
        if (W > 480 || d.getUTCHours() % 12 === 0) c.fillText(lab, sx(g), H - 8);
      }
      c.strokeStyle = C.grid2; c.beginPath(); c.moveTo(m.l, base + 0.5); c.lineTo(m.l + pw, base + 0.5); c.stroke();
      if (rows) {
        var n = 0;
        rows.forEach(function (r) {
          if (r.t < t0 || r.t > t1) return;
          n++;
          var h = Math.max(4, Math.min(1, Math.log10(Math.max(100, r.depth || 300)) / 4.3) * ph);
          var x = sx(r.t), past = r.t < now;
          c.strokeStyle = past ? 'rgba(164,182,222,0.3)' : 'rgba(255,217,160,' + (0.35 + 0.5 * h / ph) + ')';
          c.lineWidth = 1.3; c.beginPath(); c.moveTo(x + 0.5, base); c.lineTo(x + 0.5, base - h); c.stroke();
        });
        $('next-count').textContent = S.n(n) + ' transits';
      }
      // now line
      c.strokeStyle = C.cool; c.lineWidth = 1.4; c.beginPath(); c.moveTo(sx(now), m.t - 6); c.lineTo(sx(now), base); c.stroke();
      c.fillStyle = C.cool; c.textAlign = 'left'; c.fillText('now', sx(now) + 5, m.t + 4);
    }, { aspect: function (w) { return w < 560 ? 0.42 : 0.2; }, animate: false });
    function cd(ms) {
      var s = Math.round(Math.abs(ms) / 1000), d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), mi = Math.floor(s % 3600 / 60), se = s % 60;
      var p2 = function (x) { return String(x).padStart(2, '0'); };
      return d ? d + 'd ' + p2(h) + 'h ' + p2(mi) + 'm' : h ? h + 'h ' + p2(mi) + 'm ' + p2(se) + 's' : mi + 'm ' + p2(se) + 's';
    }
    function localStr(ms) { try { return new Date(ms).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }); } catch (e) { return new Date(ms).toString(); } }
    function render() {
      var now = Date.now();
      var up = rows.filter(function (r) { return r.t > now; }).slice(0, 10);
      var during = rows.filter(function (r) { return Math.abs(r.t - now) < r.dur * 1800e3; }).length;
      var nc = $('next-now'); if (nc) nc.textContent = during ? '  \u00B7  ' + S.n(during) + ' in transit now' : '';
      if (!up.length) { list.innerHTML = '<li><span class="cd">&ndash;</span><span class="who">No predicted transits in the bundled window. Open the planner.</span><span></span></li>'; return; }
      list.innerHTML = up.map(function (r) {
        return '<li><span class="cd" data-t="' + r.t + '" data-dur="' + r.dur + '"></span>' +
          '<span class="who">' + X.tierDot(r.tier) + '<a href="candidates.html?q=' + encodeURIComponent(r.tic) + '">TIC ' + X.esc(r.tic) + '</a>' +
          '<span class="meta">tier ' + X.esc(r.tier) + ' &middot; P ' + X.fmt(r.P, 3) + ' d &middot; ' + (isNaN(r.depth) ? '' : Math.round(r.depth) + ' ppm &middot; ') + X.fmt(r.dur, 2) + ' h &middot; &plusmn;' + X.fmt(r.sigma, 0) + ' min</span></span>' +
          '<span class="when">' + X.esc(r.utc) + ' UTC<span>' + X.esc(localStr(r.t)) + '</span></span></li>';
      }).join('');
      tick();
    }
    function tick() {
      var now = Date.now(), need = false;
      list.querySelectorAll('.cd[data-t]').forEach(function (el) {
        var t = +el.getAttribute('data-t'), dur = +el.getAttribute('data-dur') * 3600e3;
        if (now >= t) { need = true; return; }
        el.textContent = 'in ' + cd(t - now);
      });
      if (need) render();
    }
    function useRows(r) {
      rows = r.sort(function (a, b) { return a.t - b.t; });
      render(); o.redraw();
      setInterval(tick, 1000);
      setInterval(function () { o.redraw(); }, 30000);
    }
    function fromCSV() {
      return Promise.all([X.fetchText(X.DATA.preds.site), X.fetchText(X.DATA.ephem.site)]).then(function (v) {
        var eph = X.parseCSVObjects(v[1]);
        var eMap = X.groupByTic(eph, function (r) { return r.TIC; }, function (r) { return X.num(r.period_d); });
        var now = Date.now();
        return X.parseCSVObjects(v[0]).filter(function (p) { return X.isCountedTier(p.tier); }).map(function (p) {
          var P = X.num(p.period_d), e = X.nearestByPeriod(eMap, p.TIC, P, 1e-4, 0);
          return { utc: p.tc_UTC, t: utcMs(p.tc_UTC), tic: p.TIC, tier: p.tier, P: P, sigma: X.num(p.sigma_min), dur: X.num(p.duration_h), depth: e ? X.num(e.depth_ppm) : NaN };
        }).filter(function (r) { return r.t > now - 6 * 3600e3 && r.t < now + 50 * 3600e3; });
      });
    }
    S.onView(list, function () {
      X.fetchJSON(X.DATA.upcoming.site).then(function (j) {
        var now = Date.now();
        var r = j.rows.map(function (x) { return { utc: x[0], t: utcMs(x[0]), tic: x[1], tier: x[2], P: +x[3], sigma: +x[4], dur: +x[5], depth: x[6] === '' ? NaN : +x[6] }; });
        // the bundled window must cover the next 48 hours; otherwise read predictions.csv itself
        if (utcMs(j.to_utc) < now + 48 * 3600e3) return fromCSV();
        return r;
      }).catch(fromCSV).then(useRows).catch(function (err) { X.showError(list, err); });
    }, '0px 0px 1200px 0px');
  })();

  /* ================= 09: ledger sparkline ================= */
  (function ledger() {
    var cv = $('cv-ledger'); if (!cv) return;
    var items = Array.prototype.slice.call(document.querySelectorAll('#ledger li[data-n]')).reverse();
    var pts = items.map(function (li) { return { n: +li.getAttribute('data-n'), d: li.querySelector('time').textContent.replace(' 2026', '') }; });
    var prog = S.reduced ? 1 : 0;
    var o = S.canvas(cv, function (c, W, H) {
      c.clearRect(0, 0, W, H);
      var m = { l: 40, r: 30, t: 44, b: 26 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
      var lo = 520, hi = 550;
      function sx(i) { return m.l + i / (pts.length - 1) * pw; }
      function sy(v) { return m.t + ph - (v - lo) / (hi - lo) * ph; }
      c.font = font(10); c.lineWidth = 1;
      [520, 535, 550].forEach(function (v) { c.strokeStyle = C.grid; c.beginPath(); c.moveTo(m.l, sy(v) + 0.5); c.lineTo(m.l + pw, sy(v) + 0.5); c.stroke(); c.fillStyle = C.dim; c.textAlign = 'right'; c.fillText(String(v), m.l - 6, sy(v) + 3); });
      var upto = prog * (pts.length - 1);
      c.strokeStyle = C.amberHi; c.lineWidth = 2; c.beginPath();
      for (var i = 0; i <= Math.floor(upto); i++) { if (i) c.lineTo(sx(i), sy(pts[i].n)); else c.moveTo(sx(i), sy(pts[i].n)); }
      var fi = Math.floor(upto), f = upto - fi;
      if (fi < pts.length - 1) c.lineTo(sx(fi) + (sx(fi + 1) - sx(fi)) * f, sy(pts[fi].n + (pts[fi + 1].n - pts[fi].n) * f));
      c.stroke();
      pts.forEach(function (p, i) {
        if (i > upto + 1e-6) return;
        c.fillStyle = C.well; c.strokeStyle = C.amberHi; c.beginPath(); c.arc(sx(i), sy(p.n), 3.5, 0, TAU); c.fill(); c.stroke();
        c.fillStyle = C.ink; c.textAlign = 'center'; c.fillText(String(p.n), sx(i), sy(p.n) - 9);
        c.fillStyle = C.dim; c.fillText(p.d, sx(i), H - 8);
      });
    }, { aspect: function (w) { return w < 560 ? 0.42 : 0.2; }, animate: false });
    S.onView(cv, function () { intro(1400, function (k) { prog = S.ease(k); o.redraw(); }); });
  })();
})();
