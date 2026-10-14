/* Upcoming transits: lists predicted mid-transit times from candidates/predictions.csv
 * (linear ephemeris, 1-sigma uncertainty propagated by the authors' predict.py) for a chosen window. */
(function () {
  'use strict';
  var X = window.Exo;
  var PAGE = 100;
  var $ = function (id) { return document.getElementById(id); };
  var preds = [], view = [], page = 0, ephem = null;
  var sort = { key: 't', dir: 1 };
  var DAY = 86400000;

  var COLS = [
    { key: 't', label: 'Mid-transit (UTC)', get: function (r) { return r.t; }, html: function (r) { return X.esc(r.p.tc_UTC); }, csv: function (r) { return r.p.tc_UTC; } },
    { key: 'local', label: 'Local time', get: function (r) { return r.t; }, html: function (r) { return X.esc(localStr(r.t)); }, csv: function (r) { return localStr(r.t); } },
    { key: 'sigma', label: '1σ (min)', num: true, get: function (r) { return r.sigma; }, html: function (r) { return (r.sigma > r.dur * 60 ? '<span class="warn-cell" title="1σ is longer than the transit duration">' : '<span>') + X.fmt(r.sigma, 1) + '</span>'; }, csv: function (r) { return r.sigma; } },
    { key: 'dur', label: 'Duration (h)', num: true, get: function (r) { return r.dur; }, html: function (r) { return X.fmt(r.dur, 2); }, csv: function (r) { return r.dur; } },
    { key: 'tic', label: 'TIC', num: true, get: function (r) { return Number(r.p.TIC); }, html: function (r) { return '<a href="' + X.GH.exofop(r.p.TIC) + '">' + r.p.TIC + '</a>'; }, csv: function (r) { return r.p.TIC; } },
    { key: 'tier', label: 'Tier', get: function (r) { return r.p.tier; }, html: function (r) { return X.tierDot(r.p.tier) + X.esc(r.p.tier); }, csv: function (r) { return r.p.tier; } },
    { key: 'P', label: 'P (d)', num: true, get: function (r) { return r.P; }, html: function (r) { return X.fmt(r.P, 5); }, csv: function (r) { return r.P; } },
    { key: 'epoch', label: 'Epoch', num: true, get: function (r) { return Number(r.p.epoch); }, html: function (r) { return r.p.epoch; }, csv: function (r) { return r.p.epoch; } },
    { key: 'depth', label: 'Depth (ppm)', num: true, get: function (r) { return r.e ? X.num(r.e.depth_ppm) : NaN; }, html: function (r) { return r.e ? X.fmt(X.num(r.e.depth_ppm), 0) : ''; }, csv: function (r) { return r.e ? r.e.depth_ppm : ''; } },
    { key: 'Rp', label: 'R (R⊕)', num: true, get: function (r) { return r.e ? X.num(r.e.Rp_Re) : NaN; }, html: function (r) { return r.e ? X.fmt(X.num(r.e.Rp_Re), 2) : ''; }, csv: function (r) { return r.e ? r.e.Rp_Re : ''; } },
    { key: 'Tmag', label: 'Tmag', num: true, get: function (r) { return r.e ? X.num(r.e.Tmag) : NaN; }, html: function (r) { return r.e ? X.fmt(X.num(r.e.Tmag), 2) : ''; }, csv: function (r) { return r.e ? r.e.Tmag : ''; } },
    { key: 'ra', label: 'RA (deg)', num: true, get: function (r) { return r.e ? X.num(r.e.ra) : NaN; }, html: function (r) { return r.e ? X.fmt(X.num(r.e.ra), 4) : ''; }, csv: function (r) { return r.e ? r.e.ra : ''; } },
    { key: 'dec', label: 'Dec (deg)', num: true, get: function (r) { return r.e ? X.num(r.e.dec) : NaN; }, html: function (r) { return r.e ? X.fmt(X.num(r.e.dec), 4) : ''; }, csv: function (r) { return r.e ? r.e.dec : ''; } },
    { key: 'sector', label: 'TESS sector', num: true, get: function (r) { return X.num(r.p.tess_sector); }, html: function (r) { return r.p.tess_sector; }, csv: function (r) { return r.p.tess_sector; } },
    { key: 'bjd', label: 'BJD_TDB', num: true, get: function (r) { return X.num(r.p.tc_BJD_TDB); }, html: function (r) { return r.p.tc_BJD_TDB; }, csv: function (r) { return r.p.tc_BJD_TDB; } }
  ];

  function localStr(ms) {
    try { return new Date(ms).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); }
    catch (e) { return new Date(ms).toString(); }
  }
  function utcMs(s) { return Date.parse(s.replace(' ', 'T') + ':00Z'); }

  function todayUTC() { return new Date().toISOString().slice(0, 10); }
  function readStart() {
    var v = $('start').value || todayUTC();
    var ms = Date.parse(v + 'T00:00:00Z');
    if (isNaN(ms)) ms = Date.parse(todayUTC() + 'T00:00:00Z');
    // If the chosen day is today (UTC), start from the current time so past transits are not listed.
    return v === todayUTC() ? Date.now() : ms;
  }

  function applyFilters() {
    var start = readStart(), end = start + Number($('days').value) * DAY;
    var countedOnly = $('counted').checked, tight = $('tight').checked;
    var q = $('q').value.trim().toLowerCase().replace(/^tic[\s-]*/, '');
    view = preds.filter(function (r) {
      if (r.t < start || r.t >= end) return false;
      if (countedOnly && !X.isCountedTier(r.p.tier)) return false;
      if (tight && !(r.sigma <= r.dur * 60)) return false;
      if (q && r.p.TIC.indexOf(q) < 0) return false;
      return true;
    });
    var last = NaN; preds.forEach(function (r) { if (!(r.t <= last)) last = r.t; });
    var note = '';
    if (end > last + 60000) note = 'The prediction file ends on ' + new Date(last).toISOString().slice(0, 10) + ' (UTC); later transits are not listed.';
    $('coverage').textContent = note;
    page = 0;
    applySort();
  }

  function applySort() {
    var col = COLS.filter(function (c) { return c.key === sort.key; })[0], d = sort.dir;
    view.sort(function (a, b) {
      var x = col.get(a), y = col.get(b);
      var xn = typeof x === 'number' && isNaN(x), yn = typeof y === 'number' && isNaN(y);
      if (xn || yn) return xn === yn ? 0 : (xn ? 1 : -1);
      if (x < y) return -d; if (x > y) return d;
      return a.t - b.t;
    });
    render();
  }

  function render() {
    var pages = Math.max(1, Math.ceil(view.length / PAGE));
    page = Math.min(page, pages - 1);
    var slice = view.slice(page * PAGE, page * PAGE + PAGE);
    $('thead').innerHTML = '<tr>' + COLS.map(function (c) {
      var s = sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none';
      return '<th scope="col" class="' + (c.num ? 'num' : '') + '" aria-sort="' + s + '"><button type="button" data-key="' + c.key + '">' + c.label + '</button></th>';
    }).join('') + '</tr>';
    $('tbody').innerHTML = slice.length ? slice.map(function (r) {
      return '<tr>' + COLS.map(function (c) { return '<td class="' + (c.num ? 'num' : '') + '">' + c.html(r) + '</td>'; }).join('') + '</tr>';
    }).join('') : '<tr><td colspan="' + COLS.length + '">No predicted transits in this window.</td></tr>';
    var from = view.length ? page * PAGE + 1 : 0;
    var stars = new Set(view.map(function (r) { return r.p.TIC; })).size;
    $('count').textContent = view.length + ' predicted transits of ' + stars + ' stars; showing ' + from + '–' + Math.min(view.length, page * PAGE + PAGE) + '.';
    $('page-label').textContent = 'Page ' + (page + 1) + ' of ' + pages;
    $('prev').disabled = page === 0;
    $('next').disabled = page >= pages - 1;
  }

  function toCSV() {
    var q = function (s) { s = String(s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    var cols = COLS.filter(function (c) { return c.key !== 'local'; });
    var lines = [cols.map(function (c) { return q(c.label); }).join(',')];
    view.forEach(function (r) { lines.push(cols.map(function (c) { return q(c.csv(r)); }).join(',')); });
    return lines.join('\n') + '\n';
  }

  function init(predText, ephemText) {
    var ephRows = X.parseCSVObjects(ephemText);
    var eMap = X.groupByTic(ephRows, function (r) { return r.TIC; }, function (r) { return X.num(r.period_d); });
    preds = X.parseCSVObjects(predText).map(function (p) {
      var P = X.num(p.period_d);
      return { p: p, t: utcMs(p.tc_UTC), P: P, sigma: X.num(p.sigma_min), dur: X.num(p.duration_h), e: X.nearestByPeriod(eMap, p.TIC, P, 0, 1e-5) };
    });
    $('start').value = todayUTC();
    var q0 = new URLSearchParams(location.search).get('q');
    if (q0) $('q').value = q0;
    $('filters').addEventListener('input', applyFilters);
    $('thead').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-key]'); if (!b) return;
      var k = b.getAttribute('data-key');
      if (sort.key === k) sort.dir = -sort.dir; else { sort.key = k; sort.dir = 1; }
      applySort();
    });
    $('prev').addEventListener('click', function () { page--; render(); $('table-wrap').scrollTop = 0; });
    $('next').addEventListener('click', function () { page++; render(); $('table-wrap').scrollTop = 0; });
    $('dl-view').addEventListener('click', function () {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([toCSV()], { type: 'text/csv' })); a.download = 'upcoming_transits.csv';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });
    applyFilters();
  }

  Promise.all([X.fetchText(X.DATA.preds.site), X.fetchText(X.DATA.ephem.site)])
    .then(function (v) { $('loading').remove(); init(v[0], v[1]); })
    .catch(function (err) { X.showError($('loading'), err); });
})();
