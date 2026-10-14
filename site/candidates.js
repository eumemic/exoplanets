/* Candidates page: sortable, filterable table of the two candidate CSV files. */
(function () {
  'use strict';
  var X = window.Exo;
  var PAGE = 100;
  var rows = [], view = [], page = 0, current = [];
  var sort = { key: 'P', dir: 1 };
  var $ = function (id) { return document.getElementById(id); };

  var COLS = [
    { key: 'tic', label: 'TIC', num: true, get: function (r) { return Number(r.tic); },
      html: function (r) { return '<a href="' + X.GH.exofop(r.tic) + '" title="Open TIC ' + r.tic + ' on ExoFOP">' + r.tic + '</a>'; }, csv: function (r) { return r.tic; } },
    { key: 'tier', label: 'Tier', get: function (r) { return r.tier; }, html: function (r) { return X.tierDot(r.tier) + X.esc(r.tier); }, csv: function (r) { return r.tier; } },
    { key: 'search', label: 'Search', get: function (r) { return r.search; }, html: function (r) { return r.search; }, csv: function (r) { return r.search; } },
    num('P', 'P (d)', 5), num('Rp', 'R (R⊕)', 2), num('T14', 'T14 (h)', 2), num('depth', 'Depth (ppm)', 0),
    num('MES', 'MES', 1), num('Tmag', 'Tmag', 2), num('Teff', 'Teff (K)', 0), num('dist', 'Dist (pc)', 1),
    { key: 'fpp', label: 'FPP', num: true, get: function (r) { return r.fpp; },
      html: function (r) { return isNaN(r.fpp) ? '' : '<span title="' + X.esc(r.fppKind + (isNaN(r.nfpp) ? '' : ', NFPP ' + r.nfpp)) + '">' + X.fmtFPP(r.fpp) + '</span>'; },
      csv: function (r) { return isNaN(r.fpp) ? '' : r.fpp; } },
    { key: 'hostTois', label: 'Host TOIs', optional: true, get: function (r) { return r.hostTois; }, html: function (r) { return X.esc(r.hostTois); }, csv: function (r) { return r.hostTois; }, wrap: true },
    { key: 'flags', label: 'Flags', get: function (r) { return r.flags.join('; '); }, wrap: true,
      html: function (r) { return r.flags.map(function (f) { return '<span class="tag">' + X.esc(f) + '</span>'; }).join(''); }, csv: function (r) { return r.flags.join('; '); } },
    { key: 'folder', label: 'Plots', get: function (r) { return r.folder ? 0 : 1; },
      html: function (r) { return r.folder ? '<a href="' + X.GH.tree(r.folder) + '" title="Candidate folder on GitHub: vetting plot and fit">folder</a>' : ''; },
      csv: function (r) { return r.folder ? X.GH.tree(r.folder) : ''; } }
  ];
  function num(key, label, d) {
    return { key: key, label: label, num: true, get: function (r) { return r[key]; },
      html: function (r) { return X.fmt(r[key], d); }, csv: function (r) { return isNaN(r[key]) ? '' : r[key]; } };
  }
  var activeCols = COLS;
  var open = new Set();              // keys of expanded rows
  function key(r) { return r.search + ':' + r.tic + ':' + r.P; }
  function domId(r) { return 'd-' + key(r).replace(/[^A-Za-z0-9]/g, '-'); }
  function detail(r) {
    var dl = [
      ['Tier', X.esc(r.tier) + ' (' + X.esc(r.search) + ' search)'],
      ['Period', isNaN(r.P) ? '' : X.fmt(r.P, 6) + (isNaN(r.Perr) ? '' : ' &plusmn; ' + r.Perr) + ' d'],
      ['Radius', X.fmt(r.Rp, 2) + ' R&oplus;'],
      ['Impact parameter', X.fmt(r.b, 2)], ['Duration', isNaN(r.T14) ? '' : X.fmt(r.T14, 2) + ' h'],
      ['Depth', isNaN(r.depth) ? '' : X.fmt(r.depth, 0) + ' ppm'], ['MES', X.fmt(r.MES, 1)],
      ['Tmag', X.fmt(r.Tmag, 2)], ['Teff', isNaN(r.Teff) ? '' : X.fmt(r.Teff, 0) + ' K'], ['Distance', isNaN(r.dist) ? '' : X.fmt(r.dist, 1) + ' pc'],
      ['FPP / NFPP', isNaN(r.fpp) ? '' : X.fmtFPP(r.fpp) + ' / ' + X.fmtFPP(r.nfpp) + ' <span class="muted">(' + X.esc(r.fppKind) + ')</span>'],
      ['Sky position', isNaN(r.ra) ? '' : 'RA ' + X.fmt(r.ra, 4) + '&deg;, Dec ' + X.fmt(r.dec, 4) + '&deg;'],
      ['Host TOIs', X.esc(r.hostTois)], ['Flags', X.esc(r.flags.join('; '))], ['Registered', X.esc(r.registered || '')]
    ].filter(function (x) { return x[1] && x[1] !== ' R&oplus;'; });
    var fig = r.folder
      ? '<figure><a href="' + X.GH.raw(r.folder + '/vetting.png') + '"><img src="' + X.GH.raw(r.folder + '/vetting.png') + '" loading="lazy" alt="Vetting plot of TIC ' + X.esc(r.tic) + ' at ' + X.fmt(r.P, 3) + ' d: light curve, phase-folded transit and diagnostic tests." onerror="this.closest(\'figure\').innerHTML=\'<figcaption>The vetting plot could not be loaded from GitHub.</figcaption>\'"></a>' +
        '<figcaption>Vetting plot, loaded from <code>' + X.esc(r.folder) + '/vetting.png</code> in the repository.</figcaption></figure>'
      : '<figure style="background:var(--well)"><figcaption>No candidate folder for this signal in the repository, so no vetting plot. Folders exist for tiers A, B, C, N, L1 and L.</figcaption></figure>';
    return '<div class="detail-grid">' + fig + '<div><dl>' + dl.map(function (x) { return '<dt>' + x[0] + '</dt><dd>' + x[1] + '</dd>'; }).join('') + '</dl>' +
      '<div class="detail-links">' + (r.folder ? '<a class="btn small" href="' + X.GH.tree(r.folder) + '">Folder on GitHub</a>' : '') +
      '<a class="btn small" href="' + X.GH.exofop(r.tic) + '">ExoFOP</a>' +
      (X.isCountedTier(r.tier) || r.registered ? '<a class="btn small" href="transits.html?q=' + encodeURIComponent(r.tic) + '">Predicted transits</a>' : '') + '</div></div></div>';
  }

  function readNum(id) { var v = $(id).value.trim(); return v === '' ? NaN : Number(v); }
  function checkedTiers() {
    var s = new Set();
    document.querySelectorAll('input[name="tier"]:checked').forEach(function (c) { s.add(c.value); });
    return s;
  }

  function applyFilters() {
    var q = $('q').value.trim().toLowerCase().replace(/^tic[\s-]*/, '');
    var set = $('set').value, tiers = checkedTiers();
    var pmin = readNum('pmin'), pmax = readNum('pmax'), rmin = readNum('rmin'), rmax = readNum('rmax');
    view = rows.filter(function (r) {
      if (!tiers.has(r.tier)) return false;
      if (set !== 'all' && r.search !== set) return false;
      if (!isNaN(pmin) && !(r.P >= pmin)) return false;
      if (!isNaN(pmax) && !(r.P <= pmax)) return false;
      if (!isNaN(rmin) && !(r.Rp >= rmin)) return false;
      if (!isNaN(rmax) && !(r.Rp <= rmax)) return false;
      if (q) {
        if (r.tic.indexOf(q) < 0 && r.hostTois.toLowerCase().indexOf(q) < 0) return false;
      }
      return true;
    });
    page = 0;
    applySort();
  }

  function applySort() {
    var col = COLS.filter(function (c) { return c.key === sort.key; })[0];
    var d = sort.dir;
    view.sort(function (a, b) {
      var x = col.get(a), y = col.get(b);
      var xn = (typeof x === 'number' && isNaN(x)) || x === '', yn = (typeof y === 'number' && isNaN(y)) || y === '';
      if (xn || yn) return xn === yn ? 0 : (xn ? 1 : -1); // blanks last
      if (x < y) return -d; if (x > y) return d;
      return a.P - b.P;
    });
    render();
  }

  function render() {
    var pages = Math.max(1, Math.ceil(view.length / PAGE));
    page = Math.min(page, pages - 1);
    var slice = view.slice(page * PAGE, page * PAGE + PAGE);
    var head = '<tr><th scope="col" class="x"><span class="sr">Details</span></th>' + activeCols.map(function (c) {
      var s = sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none';
      return '<th scope="col" class="' + (c.num ? 'num' : '') + '" aria-sort="' + s + '"><button type="button" data-key="' + c.key + '">' + c.label + '</button></th>';
    }).join('') + '</tr>';
    var body = slice.map(function (r, i) {
      var k = key(r), isOpen = open.has(k), id = domId(r);
      var row = '<tr><td><button type="button" class="expand" data-i="' + i + '" aria-expanded="' + isOpen + '" aria-controls="' + id + '" aria-label="Details for TIC ' + X.esc(r.tic) + ' at ' + X.fmt(r.P, 3) + ' d"></button></td>' +
        activeCols.map(function (c) { return '<td class="' + (c.num ? 'num' : '') + (c.wrap ? ' wrap' : '') + '">' + c.html(r) + '</td>'; }).join('') + '</tr>';
      if (isOpen) row += '<tr class="detail" id="' + id + '"><td colspan="' + (activeCols.length + 1) + '">' + detail(r) + '</td></tr>';
      return row;
    }).join('');
    if (!slice.length) body = '<tr><td colspan="' + (activeCols.length + 1) + '">No rows match these filters.</td></tr>';
    current = slice;
    $('table-wrap').style.setProperty('--wrapw', $('table-wrap').clientWidth + 'px');
    $('thead').innerHTML = head;
    $('tbody').innerHTML = body;
    var from = view.length ? page * PAGE + 1 : 0;
    $('count').textContent = 'Showing ' + from + '–' + Math.min(view.length, page * PAGE + PAGE) + ' of ' + view.length + ' matching rows (' + rows.length + ' in the two tables).';
    $('page-label').textContent = 'Page ' + (page + 1) + ' of ' + pages;
    $('prev').disabled = page === 0;
    $('next').disabled = page >= pages - 1;
  }

  function buildTierBoxes() {
    var present = new Set(rows.map(function (r) { return r.tier; }));
    var ids = X.TIERS.map(function (t) { return t.id; }).concat(Array.from(present).filter(function (id) { return !X.TIER_BY_ID[id]; }));
    var counts = {};
    rows.forEach(function (r) { counts[r.tier] = (counts[r.tier] || 0) + 1; });
    var params = new URLSearchParams(location.search);
    var wanted = params.get('tier') ? new Set(params.get('tier').split(',')) : null;
    ids.forEach(function (id) {
      if (!present.has(id)) return;
      var counted = X.isCountedTier(id);
      var checked = wanted ? wanted.has(id) : counted;
      var lab = document.createElement('label');
      lab.innerHTML = '<input type="checkbox" name="tier" value="' + X.esc(id) + '"' + (checked ? ' checked' : '') + '> ' + X.tierDot(id) + X.esc((X.TIER_BY_ID[id] || { name: id }).name) + ' <span class="muted">(' + counts[id] + ')</span>';
      $(counted ? 'tiers-counted' : 'tiers-other').appendChild(lab);
    });
    X.renderTierLegend($('legend'), counts);
  }

  function toCSV() {
    var q = function (s) { s = String(s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    var lines = [activeCols.map(function (c) { return q(c.label); }).join(',')];
    view.forEach(function (r) { lines.push(activeCols.map(function (c) { return q(c.csv(r)); }).join(',')); });
    return lines.join('\n') + '\n';
  }

  function init() {
    // Hide the optional host-TOI column when the table has no values for it.
    if (!rows.some(function (r) { return r.hostTois; })) activeCols = COLS.filter(function (c) { return !c.optional; });
    buildTierBoxes();
    var params = new URLSearchParams(location.search);
    if (params.get('q')) $('q').value = params.get('q');
    $('filters').addEventListener('input', applyFilters);
    $('reset').addEventListener('click', function () {
      $('filters').reset();
      document.querySelectorAll('input[name="tier"]').forEach(function (c) { c.checked = X.isCountedTier(c.value); });
      applyFilters();
    });
    $('thead').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-key]'); if (!b) return;
      var k = b.getAttribute('data-key');
      if (sort.key === k) sort.dir = -sort.dir; else { sort.key = k; sort.dir = 1; }
      applySort();
    });
    $('tbody').addEventListener('click', function (e) {
      var b = e.target.closest('button.expand'); if (!b) return;
      var r = current[+b.getAttribute('data-i')], k = key(r);
      if (open.has(k)) open.delete(k); else open.add(k);
      render();
      var nb = $('tbody').querySelector('button.expand[data-i="' + b.getAttribute('data-i') + '"]');
      if (nb) nb.focus();
    });
    $('prev').addEventListener('click', function () { page--; render(); $('table-wrap').scrollTop = 0; });
    $('next').addEventListener('click', function () { page++; render(); $('table-wrap').scrollTop = 0; });
    $('dl-view').addEventListener('click', function () {
      var blob = new Blob([toCSV()], { type: 'text/csv' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'candidates_filtered.csv';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });
    var rt; addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(render, 150); });
    applyFilters();
    if (params.get('q') && view.length && view.length <= 3) { view.forEach(function (r) { open.add(key(r)); }); render(); }
  }

  X.loadCandidates().then(function (r) { rows = r; $('loading').remove(); init(); })
    .catch(function (err) { X.showError($('loading'), err); });
})();
