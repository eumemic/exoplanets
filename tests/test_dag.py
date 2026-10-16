"""pipeline/dag: content hashes, per-function code hashes, and the runner's rebuild rules (stale inputs, parameters
and code; early cutoff; hand-edited outputs; undeclared reads and writes; checks)."""
import math
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True          # a rewritten module of the same size must never be served from a stale .pyc
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from dag import BuildError, Project  # noqa: E402
from dag.codehash import CodeIndex  # noqa: E402
from dag.hashing import FileHasher, canonical_json, sha256_json  # noqa: E402


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"))


class HashingTests(unittest.TestCase):
    def test_canonical_json_ignores_key_order_and_tags_nan(self):
        self.assertEqual(sha256_json({"a": 1, "b": [1.5, 2]}), sha256_json({"b": [1.5, 2], "a": 1}))
        self.assertNotEqual(canonical_json([math.nan]), canonical_json(["nan"]))

    def test_file_hash_follows_content(self):
        d = Path(tempfile.mkdtemp())
        f = d / "x.txt"
        f.write_text("one")
        h = FileHasher(d / "cache.json")
        first = h.file(f)
        f.write_text("two")
        self.assertNotEqual(first, h.file(f))


HELPERS = '''
"""Helpers."""
import numpy as np
SCALE = 2


def f(x):
    # a comment
    return g(x) * SCALE


def g(x):
    return x + 1


def unrelated():
    return 0


class K:
    def m(self):
        return 1
'''
USER = '''
import numpy as np
import helpers as h
from helpers import g


def a(x):
    return h.f(x)


def b(x):
    return g(x)


def c():
    return h.K().m()


def d(name):
    return getattr(h, name)()


def e():
    return np.zeros(1)
'''


class CodeHashTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        write(self.dir / "helpers.py", HELPERS)
        write(self.dir / "user.py", USER)

    def closure(self, fn):
        return CodeIndex([self.dir]).closure("user", fn)

    def test_follows_calls_across_modules(self):
        parts, _, ext = self.closure("a")
        self.assertEqual(set(parts), {"user.a", "helpers.f", "helpers.g", "helpers.SCALE"})
        self.assertEqual(ext, [])
        self.assertEqual(set(self.closure("b")[0]), {"user.b", "helpers.g"})
        self.assertIn("helpers.K", self.closure("c")[0])
        self.assertEqual(self.closure("e")[2], ["numpy"])

    def test_comments_docstrings_and_unused_code_do_not_count(self):
        before = self.closure("a")[0]
        write(self.dir / "helpers.py", HELPERS.replace("# a comment", "# another comment")
              .replace('"""Helpers."""', '"""Helpers, reworded."""').replace("return 0", "return 1"))
        self.assertEqual(before, self.closure("a")[0])

    def test_a_change_in_a_called_function_counts(self):
        before = self.closure("a")[0]
        write(self.dir / "helpers.py", HELPERS.replace("return x + 1", "return x + 2"))
        after = self.closure("a")[0]
        self.assertNotEqual(before["helpers.g"], after["helpers.g"])
        self.assertEqual(before["helpers.f"], after["helpers.f"])

    def test_dynamic_access_takes_the_whole_module(self):
        self.assertIn("helpers.unrelated", self.closure("d")[0])

    def test_module_side_effects_count(self):
        _, before, _ = self.closure("a")
        write(self.dir / "helpers.py", HELPERS + '\nimport os\nos.environ["X"] = "1"\n')
        _, after, _ = self.closure("a")
        self.assertNotEqual(before["helpers"], after["helpers"])


RULES = '''
from dag import rule, check
import lib


@rule(inputs=["data/in.txt"], outputs=["out/a.txt"], params=["scale"])
def a(ctx):
    x = int(ctx.input("data/in.txt").read_text())
    ctx.output("out/a.txt").write_text(str(lib.double(x) * ctx.param("scale")))


@rule(inputs=["out/a.txt"], outputs=["out/b.txt"])
def b(ctx):
    ctx.output("out/b.txt").write_text(ctx.input("out/a.txt").read_text() + "!")


@check(inputs=["out/b.txt"])
def b_positive(ctx):
    assert int(ctx.input("out/b.txt").read_text().rstrip("!")) > 0, "b is not positive"
'''
LIB = '''
def double(x):
    # twice
    return 2 * x
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        write(self.root / "pipeline" / "rules.py", RULES)
        write(self.root / "pipeline" / "lib.py", LIB)
        write(self.root / "pipeline" / "params.toml", "scale = 3\n")
        write(self.root / "data" / "in.txt", "2")
        self.log = []

    def project(self):
        return Project(self.root)

    def run_all(self, **kw):
        ran, failed = self.project().run(log=self.log.append, **kw)
        return ran, failed

    def states(self):
        p = self.project()
        return {n: p.status(n).state for n in p.order}

    def out(self, name):
        return (self.root / "out" / name).read_text()

    def test_first_build_then_nothing_to_do(self):
        ran, failed = self.run_all()
        self.assertEqual(ran, ["a", "b", "b_positive"])
        self.assertEqual(failed, [])
        self.assertEqual(self.out("b.txt"), "12!")
        self.assertEqual(set(self.states().values()), {"ok"})
        lock = (self.root / "dag.lock.json").read_text()
        self.assertEqual(self.run_all(), ([], []))
        self.assertEqual(lock, (self.root / "dag.lock.json").read_text())

    def test_changed_input_reruns_what_follows(self):
        self.run_all()
        write(self.root / "data" / "in.txt", "5")
        p = self.project()
        self.assertIn("input data/in.txt changed", p.status("a").reasons)
        self.assertEqual(self.run_all()[0], ["a", "b", "b_positive"])
        self.assertEqual(self.out("b.txt"), "30!")

    def test_identical_rebuilt_output_stops_the_rerun(self):
        self.run_all()
        write(self.root / "data" / "in.txt", "02")          # a new input that gives the same output
        self.assertEqual(self.run_all()[0], ["a"])

    def test_parameter_change_reruns_its_users(self):
        self.run_all()
        write(self.root / "pipeline" / "params.toml", "scale = 4\n")
        p = self.project()
        self.assertEqual(p.status("a").reasons, ["parameter scale: 3 -> 4"])
        self.assertEqual(self.run_all()[0], ["a", "b", "b_positive"])

    def test_code_change_counts_but_comments_do_not(self):
        self.run_all()
        write(self.root / "pipeline" / "lib.py", LIB.replace("# twice", "# two times"))
        self.assertEqual(set(self.states().values()), {"ok"})
        write(self.root / "pipeline" / "lib.py", LIB.replace("2 * x", "x + x + 1"))
        p = self.project()
        self.assertEqual(p.status("a").reasons, ["code lib.double changed"])
        self.run_all()
        self.assertEqual(self.out("a.txt"), "15")

    def test_hand_edited_output_stops_the_build(self):
        self.run_all()
        (self.root / "out" / "b.txt").write_text("99!")
        self.assertEqual(self.states()["b"], "edited")
        write(self.root / "data" / "in.txt", "5")
        with self.assertRaises(BuildError):
            self.run_all()
        self.run_all(discard_edits=True)
        self.assertEqual(self.out("b.txt"), "30!")

    def test_lock_check_without_the_packages(self):
        self.run_all()
        p = self.project()
        self.assertEqual(p.check_lock("b"), ([], []))
        write(self.root / "data" / "in.txt", "5")                 # changed without a rebuild
        self.assertEqual(self.project().check_lock("a")[0], ["input data/in.txt changed"])
        (self.root / "out" / "b.txt").write_text("99!")           # edited by hand
        self.assertIn("out/b.txt differs from what the build wrote", self.project().check_lock("b")[0])
        (self.root / "data" / "in.txt").unlink()                  # private data, absent on this machine
        self.assertEqual(self.project().check_lock("a"), ([], ["data/in.txt"]))

    def test_failed_check_is_recorded(self):
        write(self.root / "data" / "in.txt", "-1")
        ran, failed = self.run_all()
        self.assertEqual(failed, ["b_positive"])
        p = self.project()
        self.assertEqual(p.status("b_positive").state, "failed")
        self.assertIn("b is not positive", p.status("b_positive").reasons[0])

    def test_undeclared_read_inside_the_repository_fails(self):
        write(self.root / "data" / "other.txt", "1")
        write(self.root / "pipeline" / "rules.py", RULES.replace(
            'x = int(ctx.input("data/in.txt").read_text())',
            'x = int(ctx.input("data/in.txt").read_text()) + int(open(ctx.root / "data/other.txt").read())'))
        with self.assertRaises(BuildError) as cm:
            self.run_all()
        self.assertIn("data/other.txt", str(cm.exception))

    def test_reading_an_old_temporary_file_fails(self):
        fd, tmp = tempfile.mkstemp()
        os.write(fd, b"1")
        os.close(fd)
        write(self.root / "pipeline" / "rules.py", RULES.replace(
            'x = int(ctx.input("data/in.txt").read_text())',
            f'x = int(ctx.input("data/in.txt").read_text()) + int(open({tmp!r}).read())'))
        with self.assertRaises(BuildError) as cm:
            self.run_all()
        self.assertIn(os.path.realpath(tmp), str(cm.exception))

    def test_a_temporary_file_written_in_the_run_may_be_read(self):
        write(self.root / "pipeline" / "rules.py", RULES.replace(
            'x = int(ctx.input("data/in.txt").read_text())',
            'import tempfile, pathlib\n    t = pathlib.Path(tempfile.mkdtemp()) / "s.txt"\n    t.write_text("2")\n'
            '    x = int(ctx.input("data/in.txt").read_text()) + int(t.read_text())'))
        self.run_all()
        self.assertEqual(self.out("a.txt"), "24")

    def test_undeclared_write_fails(self):
        write(self.root / "pipeline" / "rules.py", RULES.replace(
            'ctx.output("out/b.txt").write_text(', '(ctx.root / "out" / "extra.txt").write_text("x")\n    '
            'ctx.output("out/b.txt").write_text('))
        with self.assertRaises(BuildError) as cm:
            self.run_all()
        self.assertIn("extra.txt", str(cm.exception))

    def test_undeclared_parameter_fails(self):
        write(self.root / "pipeline" / "params.toml", "scale = 3\noffset = 1\n")
        write(self.root / "pipeline" / "rules.py", RULES.replace('ctx.param("scale")', 'ctx.param("offset")'))
        with self.assertRaises(BuildError):
            self.run_all()

    def test_two_rules_with_one_output_and_cycles_are_refused(self):
        write(self.root / "pipeline" / "rules.py", RULES + '''

@rule(inputs=["data/in.txt"], outputs=["out/a.txt"])
def a2(ctx):
    pass
''')
        with self.assertRaises(BuildError):
            self.project()
        write(self.root / "pipeline" / "rules.py", RULES.replace('inputs=["data/in.txt"]', 'inputs=["out/b.txt"]'))
        with self.assertRaises(BuildError) as cm:
            self.project()
        self.assertIn("cycle", str(cm.exception))


DOC_RULES = '''
import json
from dag import rule
from dag.markers import fill


@rule(inputs=["data/numbers.json"], outputs=["README.md"], inplace={"README.md": "template"})
def readme(ctx):
    numbers = json.loads(ctx.input("data/numbers.json").read_text())
    p = ctx.output("README.md")
    p.write_text(fill(p.read_text(), numbers))


@rule(inputs=["data/items.txt"], outputs=["ledger.txt"], inplace={"ledger.txt": "ledger"})
def ledger(ctx):
    p = ctx.output("ledger.txt")
    old = p.read_text().split() if p.exists() else []
    new = [x for x in ctx.input("data/items.txt").read_text().split() if x not in old]
    p.write_text("".join(x + "\\n" for x in old + new))
'''


class InPlaceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        write(self.root / "pipeline" / "rules.py", DOC_RULES)
        write(self.root / "data" / "numbers.json", '{"n": {"total": 644}}')
        write(self.root / "data" / "items.txt", "a b")
        write(self.root / "README.md", "We have <!--n:n.total-->0<!--/n--> candidates.\n")

    def run_all(self, **kw):
        return Project(self.root).run(log=lambda *_: None, **kw)

    def test_markers_are_filled_and_prose_edits_rerun(self):
        self.run_all()
        self.assertEqual((self.root / "README.md").read_text(), "We have <!--n:n.total-->644<!--/n--> candidates.\n")
        self.assertEqual(self.run_all(), ([], []))
        write(self.root / "README.md", "Now <!--n:n.total-->644<!--/n--> candidates.\n")      # prose edit
        self.assertIn("README.md differs from what the build wrote", Project(self.root).check_lock("readme")[0])
        self.assertEqual(self.run_all()[0], ["readme"])
        write(self.root / "README.md", "Now <!--n:n.total-->700<!--/n--> candidates.\n")      # a generated value typed over
        self.assertEqual(Project(self.root).status("readme").state, "edited")
        self.run_all()
        self.assertIn("-->644<", (self.root / "README.md").read_text())
        write(self.root / "data" / "numbers.json", '{"n": {"total": 650}}')
        self.run_all()
        self.assertIn("-->650<", (self.root / "README.md").read_text())

    def test_ledger_appends_and_refuses_hand_edits(self):
        self.run_all()
        self.assertEqual((self.root / "ledger.txt").read_text(), "a\nb\n")
        self.assertEqual(self.run_all(), ([], []))
        write(self.root / "data" / "items.txt", "a b c")
        self.assertEqual(self.run_all()[0], ["ledger"])
        self.assertEqual((self.root / "ledger.txt").read_text(), "a\nb\nc\n")
        self.assertEqual(self.run_all(), ([], []))
        (self.root / "ledger.txt").write_text("a\nc\n")                                        # a row removed by hand
        with self.assertRaises(BuildError):
            self.run_all()


if __name__ == "__main__":
    unittest.main()
