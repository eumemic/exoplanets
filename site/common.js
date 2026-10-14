/* Shared helpers for the site: CSV parsing, data loading, tier definitions, formatting.
 * No dependencies. Also loadable in Node for testing (module.exports at the bottom). */
(function (root) {
  'use strict';

  var REPO = 'eumemic/exoplanets';
  var BRANCH = 'main';
  var GH = {
    repo: 'https://github.com/' + REPO,
    blob: function (p) { return 'https://github.com/' + REPO + '/blob/' + BRANCH + '/' + p; },
    tree: function (p) { return 'https://github.com/' + REPO + '/tree/' + BRANCH + '/' + p; },
    raw: function (p) { return 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH + '/' + p; },
    exofop: function (tic) { return 'https://exofop.ipac.caltech.edu/tess/target.php?id=' + tic; }
  };

  // Where each data file lives in the repository, and where build.sh puts it in the site.
  var DATA = {
    allsky:    { site: 'data/candidates_allsky.csv',        repo: 'results_public/candidates_allsky.csv' },
    earlier:   { site: 'data/tiers_earlier_candidates.csv', repo: 'results_public/tiers_earlier_candidates.csv' },
    ephem:     { site: 'data/ephemerides.csv',              repo: 'candidates/ephemerides.csv' },
    preds:     { site: 'data/predictions.csv',              repo: 'candidates/predictions.csv' },
    findability: { site: 'data/findability.csv',          repo: 'validation/findability.csv' },
    upcoming:  { site: 'data/upcoming.json' },
    folders:   { site: 'data/folders.json' },
    build:     { site: 'data/build.json' }
  };

  /* Tiers as described in the README ("Reliability tiers" and the tier table).
   * Tiers A, B, N and L1 are counted as candidates; the others are listed but not counted. */
  var TIERS = [
    { id: 'A',  counted: true,  name: 'Tier A', text: 'Several candidate signals on the star.' },
    { id: 'B',  counted: true,  name: 'Tier B', text: 'A single candidate signal on the star.' },
    { id: 'N',  counted: true,  name: 'Tier N', text: 'A TIC star within 15″ could produce the dip; passes TRICERATOPS (FPP < 0.5, NFPP < 0.1) and a centroid test, with MES ≥ 10.' },
    { id: 'L1', counted: true,  name: 'Tier L1', text: 'SNR 7.5–9 signal selected by the false-alarm classifier; passes TRICERATOPS.' },
    { id: 'C',  counted: false, name: 'Tier C', text: 'Grazing, RUWE > 1.4, MES < 10, TRICERATOPS FPP ≥ 0.5 or NFPP ≥ 0.1, or a centroid offset in all sectors. Listed, not counted.' },
    { id: 'L',  counted: false, name: 'Tier L', text: 'SNR 7.5–9, MES ≥ 9. Listed, not counted.' },
    { id: 'likely EB', counted: false, name: 'Likely binary', text: 'Likely binary. Not counted.' },
    { id: 'likely nearby FP', counted: false, name: 'Likely nearby false positive', text: 'The per-sector centroid test rejects the target and a nearby star fits. Not counted.' },
    { id: 'likely false alarm', counted: false, name: 'Likely false alarm', text: 'Likely false alarm. Not counted.' },
    { id: 'reported', counted: false, name: 'Reported elsewhere', text: 'Reported elsewhere. Not counted.' }
  ];
  /* Colour and marker shape per counted tier. Four hues cannot all be told apart under colour-vision
   * deficiency in a scatter, so every chart also encodes the tier by shape. */
  var TIER_STYLE = {
    A:  { color: '#e0a23a', shape: 'circle',   label: 'A' },
    B:  { color: '#4a90e2', shape: 'square',   label: 'B' },
    N:  { color: '#d8638f', shape: 'triangle', label: 'N' },
    L1: { color: '#25ad7e', shape: 'diamond',  label: 'L1' }
  };
  var TIER_BY_ID = {};
  TIERS.forEach(function (t) { TIER_BY_ID[t.id] = t; });
  function isCountedTier(id) { return !!(TIER_BY_ID[id] && TIER_BY_ID[id].counted); }

  /* ---------- CSV ---------- */
  function parseCSV(text) {
    var rows = [], row = [], field = '', q = false, i = 0, n = text.length;
    if (text.charCodeAt(0) === 0xFEFF) i = 1;
    for (; i < n; i++) {
      var c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else { q = false; } }
        else { field += c; }
      } else if (c === '"') { q = true; }
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
      else if (c !== '\r') { field += c; }
    }
    if (field !== '' || row.length) { row.push(field); rows.push(row); }
    return rows;
  }
  function parseCSVObjects(text) {
    var rows = parseCSV(text);
    var head = rows.shift() || [];
    var out = [];
    for (var r = 0; r < rows.length; r++) {
      var x = rows[r];
      if (x.length === 1 && x[0] === '') continue;
      var o = {};
      for (var j = 0; j < head.length; j++) o[head[j]] = x[j] === undefined ? '' : x[j];
      out.push(o);
    }
    return out;
  }

  function num(s) { return (s === undefined || s === null || s === '') ? NaN : Number(s); }
  function firstNum() {
    for (var i = 0; i < arguments.length; i++) { var x = num(arguments[i]); if (!isNaN(x)) return x; }
    return NaN;
  }

  /* ---------- Normalising the two candidate tables ---------- */
  function bestFPP(r) {
    // Prefer the Gaia-limited, centroid-combined values the README uses for the tier bar.
    var pairs = [['FPP_gc', 'NFPP_gc'], ['FPP_c', 'NFPP_c'], ['FPP', 'NFPP']];
    for (var i = 0; i < pairs.length; i++) {
      var f = num(r[pairs[i][0]]);
      if (!isNaN(f)) return { fpp: f, nfpp: num(r[pairs[i][1]]), kind: pairs[i][0] };
    }
    return { fpp: NaN, nfpp: NaN, kind: '' };
  }
  function flagList(r) {
    var f = [];
    if (r.centroid_flag) f.push(r.centroid_flag.replace('centroid offset in all sectors, ', 'centroid offset, '));
    if (r.c_reason) f.push(r.c_reason);
    if (r.fa_flag) f.push(r.fa_flag.replace('low false-alarm-classifier score', 'low FA score'));
    if (r.desert_flag) f.push(r.desert_flag);
    if (r.rv_flag && /variable|binary/i.test(r.rv_flag)) f.push(r.rv_flag);
    return f;
  }

  function normaliseFull(r) {
    var f = bestFPP(r);
    return {
      tic: r.TIC, search: 'full-sky', tier: r.tier,
      P: num(r.P_d), Perr: num(r.P_err), Rp: num(r.Rp_Re), b: num(r.b), T14: num(r.T14_h),
      depth: num(r.depth_ppm), MES: num(r.MES), Tmag: num(r.Tmag), Teff: num(r.Teff), dist: num(r.dist_pc),
      fpp: f.fpp, nfpp: f.nfpp, fppKind: f.kind, hostTois: r.host_tois || '', flags: flagList(r), folder: null
    };
  }
  function normaliseEarlier(r) {
    var f = bestFPP(r);
    return {
      tic: r.TIC, search: 'earlier', tier: r.tier,
      P: num(r.P_d), Perr: NaN, Rp: num(r.Rp_Re), b: num(r.b), T14: NaN,
      depth: NaN, MES: NaN, Tmag: NaN, Teff: NaN, dist: NaN,
      fpp: f.fpp, nfpp: f.nfpp, fppKind: f.kind, hostTois: '', flags: flagList(r), folder: null
    };
  }

  /* Group rows by TIC so a signal can be matched by period. */
  function groupByTic(rows, tic, period) {
    var m = new Map();
    rows.forEach(function (r) {
      var k = tic(r);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push({ p: period(r), r: r });
    });
    return m;
  }
  function nearestByPeriod(map, tic, P, relTol, absTol) {
    var list = map.get(String(tic));
    if (!list) return null;
    var best = null, bd = Infinity;
    for (var i = 0; i < list.length; i++) {
      var d = Math.abs(list[i].p - P);
      if (d < bd) { bd = d; best = list[i].r; }
    }
    var tol = Math.max(absTol || 0, (relTol || 0) * P);
    return best && bd <= tol ? best : null;
  }

  /* Folder names look like TIC100624547_P1.922 (period rounded to 3 decimals). */
  function folderIndex(folders) {
    var m = new Map();
    function add(names, base) {
      (names || []).forEach(function (name) {
        var x = /^TIC(\d+)_P([0-9.]+)$/.exec(name);
        if (!x) return;
        if (!m.has(x[1])) m.set(x[1], []);
        m.get(x[1]).push({ p: Number(x[2]), path: base + name });
      });
    }
    return { m: m, add: add };
  }
  function findFolder(idx, tic, P) {
    var list = idx.get(String(tic));
    if (!list) return null;
    var best = null, bd = Infinity;
    for (var i = 0; i < list.length; i++) {
      var d = Math.abs(list[i].p - P);
      if (d < bd) { bd = d; best = list[i]; }
    }
    return best && bd <= 0.0011 ? best.path : null;
  }

  /* Build the combined candidate list from already-fetched text. */
  function buildCandidates(allskyText, earlierText, ephemText, folders) {
    var full = parseCSVObjects(allskyText).map(normaliseFull);
    var earlier = parseCSVObjects(earlierText).map(normaliseEarlier);
    var ephem = ephemText ? parseCSVObjects(ephemText) : [];
    var eMap = groupByTic(ephem, function (r) { return r.TIC; }, function (r) { return num(r.period_d); });
    earlier.forEach(function (r) {
      var e = nearestByPeriod(eMap, r.tic, r.P, 0.002, 0);
      if (e) { r.T14 = num(e.duration_h); r.depth = num(e.depth_ppm); r.Tmag = num(e.Tmag); }
    });
    // Sky position and registration date, from the ephemeris table (registered candidates only).
    full.concat(earlier).forEach(function (r) {
      var e = nearestByPeriod(eMap, r.tic, r.P, 0.002, 0);
      r.ra = e ? num(e.ra) : NaN; r.dec = e ? num(e.dec) : NaN; r.registered = e ? e.registered : '';
    });
    var fi = folderIndex();
    var fiEarlier = folderIndex();
    if (folders) {
      fi.add(folders.allsky, 'candidates/allsky/');
      fiEarlier.add(folders.earlier, 'candidates/');
      // Fallbacks: earlier-search rows may live under allsky/ and vice versa.
      fiEarlier.add(folders.allsky, 'candidates/allsky/');
      fi.add(folders.earlier, 'candidates/');
    }
    full.forEach(function (r) { r.folder = findFolder(fi.m, r.tic, r.P); });
    earlier.forEach(function (r) { r.folder = findFolder(fiEarlier.m, r.tic, r.P); });
    return full.concat(earlier);
  }

  function fetchText(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (res) {
      if (!res.ok) throw new Error(url + ': HTTP ' + res.status);
      return res.text();
    });
  }
  function fetchJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (res) {
      if (!res.ok) throw new Error(url + ': HTTP ' + res.status);
      return res.json();
    });
  }
  function loadCandidates() {
    return Promise.all([
      fetchText(DATA.allsky.site), fetchText(DATA.earlier.site),
      fetchText(DATA.ephem.site).catch(function () { return ''; }),
      fetchJSON(DATA.folders.site).catch(function () { return null; })
    ]).then(function (v) { return buildCandidates(v[0], v[1], v[2], v[3]); });
  }

  /* ---------- Formatting ---------- */
  function fmt(x, d) { return (x === undefined || isNaN(x)) ? '' : x.toFixed(d); }
  function fmtFPP(x) {
    if (isNaN(x)) return '';
    if (x === 0) return '0';
    if (x < 0.0005) return '<0.001';
    return x.toFixed(3);
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function median(a) {
    var v = a.filter(function (x) { return !isNaN(x); }).sort(function (x, y) { return x - y; });
    if (!v.length) return NaN;
    var m = v.length >> 1;
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }
  /* Small inline marker matching the charts: colour and shape per counted tier, a hollow ring otherwise. */
  function tierDot(id) {
    var st = TIER_STYLE[id], d;
    if (!st) return '<svg class="tier-dot" viewBox="0 0 12 12" aria-hidden="true"><circle cx="6" cy="6" r="3.6" fill="none" stroke="#8e97ab" stroke-width="1.3"/></svg>';
    if (st.shape === 'circle') d = '<circle cx="6" cy="6" r="4.4"/>';
    else if (st.shape === 'square') d = '<rect x="2" y="2" width="8" height="8" rx="1"/>';
    else if (st.shape === 'triangle') d = '<path d="M6 1.2 L10.8 10 H1.2 Z"/>';
    else d = '<path d="M6 0.8 L11.2 6 L6 11.2 L0.8 6 Z"/>';
    return '<svg class="tier-dot" viewBox="0 0 12 12" aria-hidden="true" fill="' + st.color + '">' + d + '</svg>';
  }

  function renderTierLegend(el, counts) {
    var html = '<dl class="legend">';
    TIERS.forEach(function (t) {
      var c = counts && counts[t.id] !== undefined ? ' <span class="muted">(' + counts[t.id].toLocaleString('en-US') + ' rows)</span>' : '';
      html += '<dt>' + tierDot(t.id) + esc(t.name) + (t.counted ? ' <span class="tag t-live">counted</span>' : ' <span class="tag">not counted</span>') + c + '</dt><dd>' + esc(t.text) + '</dd>';
    });
    el.innerHTML = html + '</dl>';
  }

  /* Footer build stamp (commit and date written by build.sh). */
  function fillBuildInfo() {
    var el = document.getElementById('build-info');
    if (!el) return;
    fetchJSON(DATA.build.site).then(function (b) {
      var link = b.commit ? ' <a href="' + GH.repo + '/commit/' + esc(b.commit) + '">' + esc(String(b.commit).slice(0, 7)) + '</a>' : '';
      el.innerHTML = 'Built from commit' + link + ' on ' + esc(b.built || '') + '.';
    }).catch(function () { /* optional */ });
  }
  function showError(el, err) {
    el.innerHTML = '<p class="error" role="alert">Could not load the data (' + esc(err && err.message || err) + '). The files are in the <a href="' + GH.repo + '">repository</a>.</p>';
  }

  var api = {
    GH: GH, DATA: DATA, TIERS: TIERS, TIER_STYLE: TIER_STYLE, TIER_BY_ID: TIER_BY_ID, isCountedTier: isCountedTier,
    parseCSV: parseCSV, parseCSVObjects: parseCSVObjects, num: num, firstNum: firstNum,
    buildCandidates: buildCandidates, loadCandidates: loadCandidates, fetchText: fetchText, fetchJSON: fetchJSON,
    groupByTic: groupByTic, nearestByPeriod: nearestByPeriod,
    fmt: fmt, fmtFPP: fmtFPP, esc: esc, median: median, tierDot: tierDot,
    renderTierLegend: renderTierLegend, fillBuildInfo: fillBuildInfo, showError: showError
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Exo = api;
})(typeof window !== 'undefined' ? window : globalThis);
