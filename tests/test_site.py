"""The website: its numbers come from pipeline/site_data.py, which passes on results_public/numbers.json (the build's
numbers, which the documents also quote) with the funnel and the release notes; none is typed into a page."""
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline'))
import site_data  # noqa: E402

SITE = ROOT / 'site'
PAGES = sorted(SITE.glob('*.html'))


class Text(HTMLParser):
    """Visible text of a page, without scripts and styles."""
    def __init__(self):
        super().__init__()
        self.skip, self.parts = 0, []

    def handle_starttag(self, tag, attrs):
        self.skip += tag in ('script', 'style')

    def handle_endtag(self, tag):
        self.skip -= tag in ('script', 'style')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(path):
    p = Text()
    p.feed(path.read_text())
    return ' '.join(p.parts)


def summary():
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / 'summary.json'
        argv, sys.argv = sys.argv, ['site_data.py', str(out)]
        try:
            site_data.main()
        finally:
            sys.argv = argv
        return json.loads(out.read_text())


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = summary()

    def test_counts_match_the_tables(self):
        import csv
        rows = list(csv.DictReader(open(ROOT / 'results_public' / 'candidates_allsky.csv')))
        earlier = list(csv.DictReader(open(ROOT / 'results_public' / 'tiers_earlier_candidates.csv')))
        n = sum(r['tier'] in ('M', 'S', 'N', 'L1') for r in rows) + sum(r['tier'] in ('M', 'S') for r in earlier)
        self.assertEqual(self.s['numbers']['catalog']['counted']['total'], n)

    def test_latest_release_note_gives_the_current_total(self):
        latest = next(r for r in self.s['releases'] if r['count'] is not None)
        self.assertEqual(latest['count'], self.s['numbers']['catalog']['counted']['total'],
                         'the newest dated release note in README.md should state the current number of candidates')

    def test_funnel_stages_decrease(self):
        for p in ('full-sky search', 'QLP re-search'):
            f = self.s['funnel'][p]['hi']
            seq = [f['prefilter'], f['leo_pass'], f['cuts']]
            self.assertEqual(seq, sorted(seq, reverse=True), p)
            self.assertEqual(f['cuts'], f['offset'] + f['no_image'] + f['close_nb'] + f['clean'], p)

    def test_bindings_resolve(self):
        for page in PAGES:
            for key in re.findall(r'data-k="([^"]+)"', page.read_text()):
                key = key.replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')
                v = site_data_pick(self.s, key)
                self.assertIsInstance(v, (int, float), f'{page.name}: data-k="{key}"')


def site_data_pick(obj, path):
    for k in path.split('/'):
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


class NoTypedResultsTests(unittest.TestCase):
    # A page may state method settings, literature values, sector numbers (up to 104), identifiers and years as text.
    # Results (counts, rates, medians) are filled in from the summary or the tables when the page loads.
    def test_no_large_or_separated_numbers_in_page_text(self):
        for page in PAGES:
            text = visible_text(page)
            # numbers standing alone (not inside a file name or identifier such as toi4342.png)
            for m in re.finditer(r'(?:TIC|TOI)[\s-]?\d+|(?<![\w.])\d[\d,.]*\d(?!\w)|(?<![\w.])\d(?!\w)', text):
                tok = m.group(0)
                if tok.startswith(('TIC', 'TOI')):
                    continue
                self.assertNotRegex(tok, r'\d,\d{3}', f'{page.name}: "{tok}" looks like a typed count')
                if re.fullmatch(r'\d+', tok):
                    self.assertTrue(int(tok) <= 104 or re.fullmatch(r'(?:19|20)\d\d', tok),
                                    f'{page.name}: "{tok}" looks like a typed count')

    def test_no_signature_link(self):
        for page in list(PAGES) + [SITE / 'style.css']:
            self.assertNotIn('askaconsult', page.read_text().lower(), page.name)


if __name__ == '__main__':
    unittest.main()
