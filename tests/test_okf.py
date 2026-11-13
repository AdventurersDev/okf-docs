"""Tests for the okf-docs helper script. Run from the repository root:

    python3 -m unittest discover tests

The fixtures live in okf-docs/evals/fixtures/, shared with the plugin's eval suite. They are copied
to a temporary folder for each test, with a private HOME, so tests never touch the fixtures or your
own settings. Git tests are skipped when git isn't installed.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "okf-docs" / "skills" / "okf-docs" / "scripts" / "okf.py"
FIXTURES = HERE.parent / "okf-docs" / "evals" / "fixtures"
sys.path.insert(0, str(SCRIPT.parent))
import okf  # noqa: E402

UTC = dt.timezone.utc
AT = dt.datetime(2026, 11, 12, 12, 0, tzinfo=UTC)  # the clock for in-process checks
OLD = dt.datetime(2026, 10, 1, tzinfo=UTC).timestamp()  # mtime given to copied fixture files
HAS_GIT = shutil.which("git") is not None

DEPLOY_DOC = """---
type: runbook
title: Deploy
description: Deploy with the release pipeline; roll back from the same page.
---

# Deploy

1. Run the release pipeline.
"""

IMPORT_DOC = """---
type: concept
title: Data import
description: Import CSV files into a workspace.
---

# Data import

Owners import CSV files from Settings → Import.
"""

NEW_OBSERVATION = """---
type: metric
x-okfdocs-class: observation
title: Export volume doubled
description: Weekly exports doubled between September and October.
stale_after: 2027-02-01T00:00:00Z
---

# Export volume doubled

Weekly exports doubled between September and October.
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="okf-test-")).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self._environ = dict(os.environ)
        os.environ.update({
            "HOME": str(self.home), "USERPROFILE": str(self.home), "OKF_ACTOR": "tester", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
            # Hooks without --state fall back to the temp folder: keep it per test.
            "TMPDIR": str(self.tmp), "TEMP": str(self.tmp), "TMP": str(self.tmp),
        })

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._environ)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, name):
        dst = self.tmp / name
        shutil.copytree(FIXTURES / name, dst)
        for p in [dst] + list(dst.rglob("*")):
            os.utime(p, (OLD, OLD))
        return dst

    def project(self, root):
        return okf.Project.find(root)

    def ctx(self, project, at=AT):
        return okf.Ctx(project, at=at)

    def findings(self, root):
        project = self.project(root)
        ctx = self.ctx(project)
        out = []
        for b in project.bundles:
            for d in b.docs:
                out += okf.check_doc(d, ctx)
            out += okf.check_bundle(b, ctx)
        return out

    def edit(self, path, old, new, count=1):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, count), encoding="utf-8")

    def codes(self, root, path):
        return {f.code for f in self.findings(root) if f.path == path}

    def doc(self, root, rel):
        project = self.project(root)
        return okf.Doc.load(project.bundle_for(root / rel), root / rel)

    def cli(self, *args, cwd=None, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPT)] + list(args), cwd=str(cwd or self.tmp), input=stdin,
                              capture_output=True, text=True, encoding="utf-8", env=dict(os.environ), timeout=120)

    def git(self, cwd, *args, date=None):
        env = dict(os.environ)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
        res = subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main",
                              "-c", "core.hooksPath=/dev/null"] + list(args),
                             cwd=str(cwd), capture_output=True, text=True, env=env, check=True)
        return res.stdout.strip()


class TestYAML(Base):
    def test_block_structures(self):
        text = ("a: 1\n"
                "b:\n"
                "- x\n"
                "- y\n"
                "c:\n"
                "  d: [1, two, {e: f}]\n"
                "  g:\n"
                "    - h: 1\n"
                "      i: 2\n"
                "    - - nested\n"
                "      - list\n"
                "empty:\n"
                "flow_empty: []\n")
        data, warnings = okf.yaml_load(text)
        self.assertEqual(data, {"a": 1, "b": ["x", "y"],
                                "c": {"d": [1, "two", {"e": "f"}], "g": [{"h": 1, "i": 2}, ["nested", "list"]]},
                                "empty": None, "flow_empty": []})
        self.assertEqual(warnings, [])

    def test_scalars(self):
        text = ('dq: "tab\\there \\"q\\" \\u00e9"\n'
                "sq: 'it''s'\n"
                "int: 42\n"
                "neg: -7\n"
                "float: 0.5\n"
                "ver: 0.9.1\n"
                "yes_str: yes\n"
                "t: true\n"
                "n: null\n"
                "tilde: ~\n"
                "ts: 2026-11-12T14:03:22+01:00\n"
                "date: 2026-11-12\n"
                "url: https://example.com/a#b\n"
                "hash: a #comment\n"
                "colon: a:b\n")
        data, _ = okf.yaml_load(text)
        self.assertEqual(data, {"dq": 'tab\there "q" é', "sq": "it's", "int": 42, "neg": -7, "float": 0.5,
                                "ver": "0.9.1", "yes_str": "yes", "t": True, "n": None, "tilde": None,
                                "ts": "2026-11-12T14:03:22+01:00", "date": "2026-11-12",
                                "url": "https://example.com/a#b", "hash": "a", "colon": "a:b"})

    def test_multiline_and_block_scalars(self):
        text = ("plain: first line\n"
                "  second line\n"
                "\n"
                "  after blank\n"
                "lit: |\n"
                "  line 1\n"
                "    indented\n"
                "  line 3\n"
                "\n"
                "fold: >-\n"
                "  folded\n"
                "  text\n"
                "keep: |+\n"
                "  k\n"
                "\n"
                "end: 1\n")
        data, _ = okf.yaml_load(text)
        self.assertEqual(data["plain"], "first line second line\nafter blank")
        self.assertEqual(data["lit"], "line 1\n  indented\nline 3\n")
        self.assertEqual(data["fold"], "folded text")
        self.assertEqual(data["keep"], "k\n\n")
        self.assertEqual(data["end"], 1)

    def test_multiline_flow_and_comments(self):
        data, _ = okf.yaml_load("# top\ntags: [a,\n  b, c] # tail\nmeta: { x: 1,\n  y: [2, 3] }\n"
                                "b:\n  # inner\n  - x # ex\n")
        self.assertEqual(data, {"tags": ["a", "b", "c"], "meta": {"x": 1, "y": [2, 3]}, "b": ["x"]})

    def test_errors(self):
        saved, okf._pyyaml = okf._pyyaml, None
        try:
            for text in ("a:\n\t- x\n", "a: &anchor 1\n", "a: [1, 2\n", 'a: "open\n', "- a\nb: 1\n"):
                with self.assertRaises(okf.YAMLError, msg=repr(text)):
                    okf.yaml_load(text)
        finally:
            okf._pyyaml = saved

    def test_unquoted_colon_warns(self):
        data, warnings = okf.yaml_load("description: Who we serve: ops teams\n")
        self.assertEqual(data["description"], "Who we serve: ops teams")
        self.assertEqual(len(warnings), 1)

    def test_colon_inside_flow_warns(self):
        for text in ("generated: { by: human:alex, at: 2026-11-12T14:03:22+01:00 }\n",
                     "tags: [a, https://example.com]\n"):
            data, warnings = okf.yaml_load(text)
            self.assertEqual(len(warnings), 1, text)
            self.assertIn("block style", warnings[0])
        for text in ('tags: [a, "b:c"]\n', "meta: { x: 1, y: [2, 3] }\n"):
            self.assertEqual(okf.yaml_load(text)[1], [], text)
        root = self.fixture("repo")
        (root / "docs" / "product" / "data-import.md").write_text(IMPORT_DOC.replace(
            "---\n\n", "generated: { by: human:alex, at: 2026-11-12T14:03:22+01:00 }\n---\n\n", 1), encoding="utf-8")
        flagged = {(f.path, f.code) for f in self.findings(root)}
        self.assertIn(("docs/product/data-import.md", "yaml-strict"), flagged)

    def test_dump_round_trip(self):
        data = {
            "type": "concept", "title": "Data: export", "description": "Uses # and 'quotes' and \"dq\"",
            "tags": ["a", "b c", "yes", "1.5", "x,y"], "n": 3, "f": 0.25, "b": False, "none": None,
            "generated": {"by": "okf-docs/1.0.5", "at": "2026-11-12T14:03:22+01:00"},
            "verified": [{"by": "human:alex", "at": "2026-11-12T16:40:00+01:00"}],
            "sources": [{"id": "job", "resource": "../../src/export/job.ts"},
                        {"resource": "https://example.com/x?a=1"}],
            "nested": {"deep": {"list": [[1, 2], {"k": "v"}], "text": "line one\nline two\n"}},
            "empty_list": [], "empty_map": {}, "version": "0.3", "colon_end": "Note:", "dash": "- not a list",
        }
        text = "\n".join(okf.yaml_dump(data)) + "\n"
        back, warnings = okf.yaml_load(text)
        self.assertEqual(back, data)
        self.assertEqual(warnings, [])
        self.assertIn("generated:\n  by: okf-docs/1.0.5\n  at: 2026-11-12T14:03:22+01:00\n", text)
        self.assertIn("verified:\n  - by: human:alex\n    at: 2026-11-12T16:40:00+01:00\n", text)
        self.assertIn("sources:\n  - id: job\n    resource: ../../src/export/job.ts\n", text)
        self.assertIn("nested:\n  deep:\n    list:\n      - [1, 2]\n      - k: v\n", text)
        self.assertNotIn("{ ", text)
        if okf._pyyaml is not None:
            self.assertEqual(okf._pyyaml_load(text), data)

    @unittest.skipUnless(okf._pyyaml is not None, "PyYAML not installed")
    def test_matches_pyyaml_on_fixtures(self):
        for path in sorted(FIXTURES.rglob("*.md")):
            fm, _, _, _ = okf.split_frontmatter(path.read_text(encoding="utf-8"))
            if fm is not None:
                self.assertEqual(okf._Parser(fm).parse(), okf._pyyaml_load(fm), path)


class TestTime(unittest.TestCase):
    def test_parse_ts(self):
        t, p = okf.parse_ts("2026-11-12T14:03:22+01:00")
        self.assertIsNone(p)
        self.assertEqual(t.utcoffset(), dt.timedelta(hours=1))
        self.assertEqual(okf.parse_ts("2026-11-12T13:03:22Z")[0], dt.datetime(2026, 11, 12, 13, 3, 22, tzinfo=UTC))
        t, p = okf.parse_ts("2026-11-12T14:03:22.123-0530")
        self.assertEqual((p, t.utcoffset()), (None, -dt.timedelta(hours=5, minutes=30)))
        self.assertEqual(okf.parse_ts("2026-11-12")[1], okf.DATE_ONLY)  # valid OKF 0.3; callers decide what to say
        self.assertEqual(okf.parse_ts("2026-11-12")[0], dt.datetime(2026, 11, 12, tzinfo=UTC))
        self.assertEqual(okf.parse_ts("2026-11-12T14:03:22")[1], okf.NO_OFFSET)
        self.assertEqual(okf.parse_ts(dt.date(2026, 1, 2))[1], okf.DATE_ONLY)
        self.assertEqual(okf.parse_ts("2026-13-40"), (None, "not a valid date"))
        self.assertIsNone(okf.parse_ts("yesterday")[0])

    def test_parse_duration(self):
        self.assertEqual(okf.parse_duration("90d"), 90)
        self.assertEqual(okf.parse_duration("2w"), 14)
        self.assertAlmostEqual(okf.parse_duration("12mo"), 365.28, places=2)
        self.assertEqual(okf.parse_duration("1 year"), 365.25)
        self.assertEqual(okf.parse_duration("never"), math.inf)
        self.assertIsNone(okf.parse_duration("soon"))


class TestCheck(Base):
    def test_clean_repo_has_no_problems(self):
        problems = [f.to_dict() for f in self.findings(self.fixture("repo")) if f.severity != "info"]
        self.assertEqual(problems, [])

    def test_review_queue(self):
        info = {(f.path, f.code) for f in self.findings(self.fixture("repo")) if f.severity == "info"}
        self.assertIn(("docs/system/architecture.md", "unverified"), info)
        self.assertIn(("help/export-your-data.md", "unverified"), info)
        self.assertNotIn(("docs/decisions/001-csv-first.md", "unverified"), info)  # deprecated: not queued

    def test_legacy_findings(self):
        root = self.fixture("legacy")
        codes = {(f.path, f.code) for f in self.findings(root)}
        for expected in [("docs/index.md", "okf-version"), ("docs/product/index.md", "index-frontmatter"),
                         ("docs/product/invoices.md", "timestamp-date-only"),
                         ("docs/product/invoices.md", "actor-format"),
                         ("docs/product/invoices.md", "sources-format"),
                         ("docs/product/invoices.md", "source-path"),
                         ("docs/product/invoices.md", "legacy-key"),
                         ("docs/product/refunds.md", "timestamp-format")]:
            self.assertIn(expected, codes)
        project = self.project(root)
        self.assertEqual([b.rel for b in project.bundles], ["docs/"])  # found without a config
        self.assertTrue(all(okf.is_v3(d) for d in project.bundles[0].docs))

    def test_autodetects_docs_folder_without_okf_version(self):
        root = self.fixture("legacy")
        (root / "docs/index.md").write_text("# Sections\n\n* [Product](product/) - Invoicing.\n", encoding="utf-8")
        self.assertEqual([b.rel for b in self.project(root).bundles], ["docs/"])

    def test_brain_lifecycle(self):
        found = self.findings(self.fixture("brain-repo"))
        self.assertEqual(sorted(f.path for f in found if f.code == "delete-candidate"),
                         ["brain/observations/2026-06-01-exports-too-slow.md",
                          "brain/observations/2026-10-15-teams-want-sso.md"])
        self.assertEqual([f.to_dict() for f in found if f.severity != "info" and f.code != "delete-candidate"], [])
        self.assertFalse([f for f in found if f.code == "unverified" and "/assets/" in f.path])

    def test_broken_link_and_missing_source(self):
        root = self.fixture("repo")
        doc = root / "docs/product/data-export.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("(../system/architecture.md)", "(../system/gone.md)")
                       .replace("resource: ../../src/export/job.ts", "resource: ../../src/export/missing.ts"), encoding="utf-8")
        codes = [f.code for f in self.findings(root) if f.path == "docs/product/data-export.md"]
        self.assertIn("link-broken", codes)
        self.assertIn("source-missing", codes)

    def test_files_without_a_type_are_not_concepts(self):
        root = self.fixture("repo")
        (root / "docs/product/notes.md").write_text("# Notes\n\nNo frontmatter.\n", encoding="utf-8")
        (root / "docs/product/typeless.md").write_text("---\ntitle: Typeless\n---\n\n# Typeless\n", encoding="utf-8")
        for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "CLAUDE.md", "SKILL.md"):
            (root / "docs" / name).write_text("# %s\n" % name, encoding="utf-8")
        (root / "docs/product/README.md").write_text("---\ntitle: Readme\n---\n", encoding="utf-8")
        found = {f.path: f for f in self.findings(root) if f.code == "not-a-concept"}
        self.assertEqual(set(found), {"docs/product/notes.md", "docs/product/typeless.md"})
        for f in found.values():
            self.assertEqual((f.level, f.severity), ("okf", "warn"))
        self.assertFalse([f for f in self.findings(root) if f.path.endswith(("README.md", "AGENTS.md", "CLAUDE.md"))])
        self.assertFalse([f for f in self.findings(root) if f.severity == "error"])
        # a non-concept never reaches the index
        project = self.project(root)
        text, _ = okf.build_index(project.bundles[0], root / "docs/product", self.ctx(project))
        self.assertNotIn("notes.md", text)
        self.assertNotIn("README.md", text)
        self.assertEqual(self.cli("check", cwd=root).returncode, 0)

    def test_dot_files_and_folders_are_not_part_of_the_bundle(self):
        root = self.fixture("repo")
        (root / "docs/.drafts").mkdir()
        (root / "docs/.drafts/idea.md").write_text("no frontmatter\n", encoding="utf-8")
        (root / "docs/product/.hidden.md").write_text("---\ntype: concept\n---\n", encoding="utf-8")
        paths = {d.rel for d in self.project(root).bundles[0].docs}
        self.assertFalse([p for p in paths if "idea" in p or "hidden" in p], paths)
        self.assertFalse([f for f in self.findings(root) if "idea" in f.path or "hidden" in f.path])

    def test_page_citing_internal_file(self):
        root = self.fixture("repo")
        doc = root / "docs/product/data-export.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("visibility: public\n", ""), encoding="utf-8")
        self.assertIn(("help/export-your-data.md", "public-source-internal"),
                      {(f.path, f.code) for f in self.findings(root)})

    def test_team_update_may_be_internal(self):
        root = self.fixture("repo")
        (root / "help" / "2026-11-10-week-45.md").write_text(
            "---\ntype: update\ntitle: Week 45\ndescription: Export jobs shipped; SSO next.\n"
            "sources:\n  - resource: ../docs/system/architecture.md\n---\n\n# Week 45\n\n## Progress\n\n"
            "- Export jobs shipped.\n", encoding="utf-8")
        codes = {f.code for f in self.findings(root) if f.path == "help/2026-11-10-week-45.md"}
        self.assertFalse(codes & {"page-visibility", "public-source-internal"}, codes)

    def test_site_voice_file_stays_internal(self):
        root = self.fixture("repo")
        (root / "help" / "voice.md").write_text(
            "---\ntype: voice\ntitle: Voice for the help center\n"
            "description: Admins reading the help center; plain and friendly; en-US.\n---\n\n"
            "# Voice for the help center\n\n## Reader\n\nWorkspace admins.\n", encoding="utf-8")
        codes = {f.code for f in self.findings(root) if f.path == "help/voice.md"}
        self.assertNotIn("page-visibility", codes)

    def test_bundles_never_share_or_nest_folders(self):
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        base = cfg.read_text(encoding="utf-8")
        self.assertNotIn("bundle-overlap", {f.code for f in self.findings(root)})
        for extra, where in (("  - path: docs\n    kind: brain\n", "same folder as the docs bundle"),
                             ("  - path: docs/brain\n    kind: brain\n", "inside the docs bundle docs/")):
            (root / "docs" / "brain").mkdir(exist_ok=True)
            cfg.write_text(base.replace("links: relative", extra + "links: relative", 1), encoding="utf-8")
            msgs = [f.message for f in self.findings(root) if f.code == "bundle-overlap"]
            self.assertEqual(len(msgs), 1, msgs)
            self.assertIn(where, msgs[0])

    def test_rooted_link_style(self):
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("links: relative", "links: rooted"), encoding="utf-8")
        self.assertTrue([f for f in self.findings(root)
                         if f.code == "link-style" and f.path == "docs/product/data-export.md"])
        (root / "docs/product/data-import.md").write_text(IMPORT_DOC, encoding="utf-8")
        project = self.project(root)
        text, _ = okf.build_index(project.bundles[0], root / "docs/product", self.ctx(project))
        self.assertIn("* [Data import](/product/data-import.md)", text)
        self.assertIn("* [Data export](data-export.md)", text)  # existing entries keep their links

    def test_decisions_supersede_both_ways(self):
        root = self.fixture("repo")
        d2 = root / "docs/decisions/002-json-export.md"
        d2.write_text(d2.read_text(encoding="utf-8").replace("supersedes: 001-csv-first.md\n", ""), encoding="utf-8")
        self.assertIn(("docs/decisions/001-csv-first.md", "supersede-mutual"),
                      {(f.path, f.code) for f in self.findings(root)})

    def test_fix_repairs_indexes_and_log(self):
        root = self.fixture("legacy")
        (root / "docs/log.md").unlink()
        r = self.cli("check", "--fix", cwd=root)
        self.assertIn("fixed  docs/log.md", r.stdout)
        self.assertEqual((root / "docs/index.md").read_text(encoding="utf-8").split("---")[1].strip(),
                         'okf_version: "0.3"\ntitle: Docs')  # the root frontmatter stays, the version moves
        self.assertFalse((root / "docs/product/index.md").read_text(encoding="utf-8").startswith("---"))
        codes = {f.code for f in self.findings(root)}
        self.assertFalse(codes & {"index-frontmatter", "log-missing", "index-stale"})


class TestIndex(Base):
    def test_fixture_indexes_are_current(self):
        for name in ("repo", "brain-repo"):
            root = self.fixture(name)
            project = self.project(root)
            for b in project.bundles:
                for d in b.dirs_with_docs():
                    text, _ = okf.build_index(b, d, self.ctx(project))
                    self.assertEqual(text.strip(), (d / "index.md").read_text(encoding="utf-8").strip(), d)

    def test_new_files_and_folders(self):
        root = self.fixture("repo")
        (root / "docs/operations").mkdir()
        (root / "docs/operations/deploy.md").write_text(DEPLOY_DOC, encoding="utf-8")
        (root / "docs/product/data-import.md").write_text(IMPORT_DOC, encoding="utf-8")
        r = self.cli("index", "--write", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        top = (root / "docs/index.md").read_text(encoding="utf-8")
        self.assertIn("* [Product](product/) - What it does: features, behavior, limits.", top)
        self.assertIn("* [Operations](operations/)\n", top)
        self.assertTrue(top.startswith('---\nokf_version: "0.3"\ntitle: Acme API docs\ndescription: How the Acme '
                                       'API works'), top)  # index --write keeps title and description
        ops = (root / "docs/operations/index.md").read_text(encoding="utf-8")
        self.assertEqual(ops, "# Runbooks\n\n* [Deploy](deploy.md) - Deploy with the release pipeline; "
                              "roll back from the same page.\n")
        product = (root / "docs/product/index.md").read_text(encoding="utf-8")
        self.assertLess(product.index("Data export"), product.index("Data import"))
        for text in (top, product):  # new entries join the existing list instead of starting a second one
            self.assertEqual(text.count("\n\n* ["), 1, text)
        self.assertIn("up to date", self.cli("index", cwd=root).stdout)
        self.assertIn(("docs/index.md", "folder-description"), {(f.path, f.code) for f in self.findings(root)})

    def test_emptied_folder_leaves_the_index(self):
        root = self.fixture("repo")
        (root / "docs/system/architecture.md").unlink()  # the only doc in system/
        found = {(f.path, f.code): f for f in self.findings(root)}
        self.assertIn("system/ (no docs left)", found[("docs/index.md", "index-stale")].message)
        self.assertIn(("docs/system/", "delete-candidate"), found)
        self.assertIn(("docs/product/data-export.md", "link-broken"), found)  # its Related link
        res = self.cli("index", "--write", cwd=root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("(system/)", (root / "docs/index.md").read_text(encoding="utf-8"))
        codes = {(f.path, f.code) for f in self.findings(root)}
        self.assertNotIn(("docs/index.md", "index-stale"), codes)
        self.assertIn(("docs/system/", "delete-candidate"), codes)  # deleting the folder stays with the user

    def test_removed_file_drops_entry_and_keeps_text(self):
        root = self.fixture("repo")
        idx = root / "docs/decisions/index.md"
        idx.write_text(idx.read_text(encoding="utf-8").replace("# Decisions\n", "# Decisions\n\nWhy the system is this way.\n"), encoding="utf-8")
        (root / "docs/decisions/001-csv-first.md").unlink()
        project = self.project(root)
        text, summary = okf.build_index(project.bundles[0], root / "docs/decisions", self.ctx(project))
        self.assertNotIn("001-csv-first.md", text)
        self.assertIn("Why the system is this way.", text)
        self.assertEqual(summary["removed"], ["001-csv-first.md"])

    def test_dated_entries_stay_newest_first(self):
        root = self.fixture("brain-repo")
        (root / "brain/observations/2026-11-01-export-volume.md").write_text(NEW_OBSERVATION, encoding="utf-8")
        project = self.project(root)
        text, _ = okf.build_index(project.bundles[0], root / "brain/observations", self.ctx(project))
        names = [line.split("](")[1].split(")")[0] for line in text.splitlines() if line.startswith("* [")]
        self.assertEqual(names, ["2026-11-01-export-volume.md", "2026-10-15-teams-want-sso.md",
                                 "2026-06-01-exports-too-slow.md"])


class TestLog(Base):
    def test_entries_and_groups(self):
        folder = self.tmp / "bundle"
        folder.mkdir()
        okf.add_log_entry(folder, "creation", "Added a.md.", today="2026-11-10")
        okf.add_log_entry(folder, "Update", "Changed  a.md\n twice.", today="2026-11-10")
        okf.add_log_entry(folder, "Deletion", "Removed b.md.", today="2026-11-12")
        self.assertEqual((folder / "log.md").read_text(encoding="utf-8"),
                         "# Directory Update Log\n\n## 2026-11-12\n\n* **Deletion**: Removed b.md.\n\n"
                         "## 2026-11-10\n\n* **Update**: Changed a.md twice.\n* **Creation**: Added a.md.\n")
        self.assertEqual(okf.check_log(folder / "log.md", okf.Project.find(folder)), [])
        self.assertEqual(okf.last_log_date(folder / "log.md"), "2026-11-12")


class TestLint(unittest.TestCase):
    def test_flags_bloat(self):
        text = ("---\ntype: concept\n---\n\n# 🚀 Overview\n\n"
                "It's important to note that this powerful feature lets you leverage exports!\n\n"
                "In order to export, basically click the button.\n\n## Details\n\n## Usage\n\nTBD\n\n"
                "## Summary\n\nIn summary, exports work.\n")
        res = okf.lint_text(text)
        found = " ".join(h["text"].lower() for h in res["hits"])
        for needle in ("important to note", "powerful", "leverage", "in order to", "basically", "in summary"):
            self.assertIn(needle, found)
        advice = " ".join(h["advice"] for h in res["hits"])
        for needle in ("emoji", "empty section", "placeholder section", "recap at the end", "exclamation"):
            self.assertIn(needle, advice)
        self.assertEqual(res["hits"][0]["line"], 5)  # line numbers count the frontmatter

    def test_bold_label_bullets(self):
        text = "# List\n\n" + "".join("- **Label %d:** text.\n" % i for i in range(5))
        self.assertIn("bold-label", " ".join(h["text"] for h in okf.lint_text(text)["hits"]))
        steps = "# Steps\n\n" + "".join("%d. **Step %d:** do it.\n" % (i, i) for i in range(1, 7))
        self.assertNotIn("bold-label", " ".join(h["text"] for h in okf.lint_text(steps)["hits"]))

    def test_quoted_phrases_are_not_linted(self):
        text = '# Style\n\nNever write "It is important to note that" or “a robust, seamless tool”.\n'
        self.assertEqual(okf.lint_text(text)["hits"], [])

    def test_clean_text_has_no_hits(self):
        text = ("# Export\n\nOwners export a workspace as CSV or JSON. Exports over 500 MB fail.\n\n"
                "## Limits\n\n- 500 MB per export.\n")
        self.assertEqual(okf.lint_text(text)["hits"], [])

    def test_ignores_code(self):
        text = "# Code\n\nRun `leverage --very` now.\n\n```\nbasically robust!\n```\n"
        self.assertEqual(okf.lint_text(text)["hits"], [])


class TestRetention(Base):
    def test_raw_file_age_comes_from_its_name(self):
        root = self.fixture("brain-repo")
        old = root / "brain" / "assets" / "files" / "2023-01-10-old-call.txt"
        old.write_text("notes\n", encoding="utf-8")
        os.utime(old, (OLD, OLD))  # a recent file time, as after a fresh clone
        found = {f.path for f in self.findings(root) if f.code == "delete-candidate"}
        self.assertIn("brain/assets/files/2023-01-10-old-call.txt", found)
        self.assertNotIn("brain/assets/files/2026-05-28-globex-call.txt", found)


class TestTemplateText(Base):
    def test_lint_and_check(self):
        hits = okf.lint_text("# Export\n\nExports <what it does, in one sentence>.\n\n<details open>\n"
                             "Run `okf.py log <bundle> <Kind>`, see <https://example.com/a b>, a <b>bold</b> word.\n"
                             "</details>\n")["hits"]
        self.assertEqual([h["text"] for h in hits if "template" in h["advice"]],
                         ["<what it does, in one sentence>"])
        root = self.fixture("repo")
        (root / "docs" / "product" / "data-import.md").write_text(
            IMPORT_DOC.replace("title: Data import", "title: <Feature name>"), encoding="utf-8")
        self.assertIn(("docs/product/data-import.md", "template-text"),
                      {(f.path, f.code) for f in self.findings(root)})


class TestUpgrade(Base):
    def test_actor_mapping(self):
        self.assertEqual(okf._upgrade_actor("agent"), "okf-docs/3")
        self.assertEqual(okf._upgrade_actor("Claude Code"), "okf-docs/3")
        self.assertEqual(okf._upgrade_actor("okf-company-brain"), "okf-docs/3")
        self.assertEqual(okf._upgrade_actor("Alex Smith"), "human:alex-smith")
        self.assertIsNone(okf._upgrade_actor("human:alex"))
        self.assertIsNone(okf._upgrade_actor("okf-docs/1.0.5"))
        self.assertIsNone(okf._upgrade_actor("team:finance"))

    def test_upgrade_legacy_bundle(self):
        root = self.fixture("legacy")
        dry = self.cli("upgrade", "--dry-run", cwd=root)
        self.assertIn("would change 4 files", dry.stdout)
        self.assertIn("credibility", (root / "docs/product/invoices.md").read_text(encoding="utf-8"))  # dry run wrote nothing
        r = self.cli("upgrade", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = okf.Doc.load(self.project(root).bundles[0], root / "docs/product/invoices.md")
        self.assertEqual(doc.fm["generated"], {"by": "okf-docs/3", "at": "2026-09-05T00:00:00Z"})
        self.assertEqual(doc.fm["verified"], [{"by": "human:alex", "at": "2026-09-06T00:00:00Z"}])
        self.assertEqual(doc.fm["sources"], [{"resource": "../../src/billing/invoice.py"}])
        self.assertFalse({"credibility", "links"} & set(doc.fm))
        self.assertIn("## Related\n\n- [Refunds](refunds.md)\n", doc.text)
        codes = {f.code for f in self.findings(root)}
        self.assertFalse(codes & {"legacy-key", "timestamp-format", "actor-format", "sources-format",
                                  "source-path", "index-frontmatter", "yaml-strict"})
        self.assertFalse([d for d in self.project(root).bundles[0].docs if okf.is_v3(d)])
        self.assertIn("changed 0 files", self.cli("upgrade", cwd=root).stdout)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_credibility_is_retired(self):
        root = self.fixture("repo")
        page = root / "docs/system/architecture.md"
        text = page.read_text(encoding="utf-8")
        for key, cred in (("x-okfdocs-credibility", "reported"), ("credibility", "inferred")):
            page.write_text(text.replace("type: design\n", "type: design\n%s: %s\n" % (key, cred), 1),
                            encoding="utf-8")
            doc = okf.Doc.load(self.project(root).bundle_for(page), page)
            self.assertEqual(doc.trust(), "unverified")  # a label is not a tier
            self.assertFalse(okf.is_v3(doc))
            self.assertTrue(okf.is_older(doc))
            self.assertIn("credibility-retired", self.codes(root, "docs/system/architecture.md"))
            out = self.cli("upgrade", cwd=root).stdout
            self.assertIn("removed `%s: %s`" % (key, cred), out)
            self.assertEqual("add a `sources` entry" in out, cred == "reported")
            self.assertNotIn("credibility", page.read_text(encoding="utf-8"))
            self.assertNotIn("credibility-retired", self.codes(root, "docs/system/architecture.md"))

    def test_credibility_verified_needs_a_human_entry(self):
        root = self.fixture("legacy")
        page = root / "docs/product/invoices.md"
        page.write_text(page.read_text(encoding="utf-8").replace("verified:\n  by: alex\n  at: 2026-09-06\n", ""),
                        encoding="utf-8")
        self.assertIn(("docs/product/invoices.md", "credibility-verified"),
                      {(f.path, f.code) for f in self.findings(root)})
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("no human `verified` entry", out)
        self.assertIn("credibility: verified", page.read_text(encoding="utf-8"))  # kept until someone confirms

    def test_draft_from_another_tool_is_still_queued(self):
        root = self.fixture("repo")
        page = root / "help/export-your-data.md"
        page.write_text(page.read_text(encoding="utf-8").replace("x-okfdocs-visibility: public",
                                                                 "x-okfdocs-visibility: public\nstatus: draft"),
                        encoding="utf-8")
        self.assertIn(("help/export-your-data.md", "draft"), {(f.path, f.code) for f in self.findings(root)})

    def test_index_holding_a_page_is_never_rewritten(self):
        root = self.fixture("brain-repo")
        bundle = self.project(root).bundles[0]
        page = self.write(bundle.root / "products/waycam/index.md",
                          "---\nx-okfdocs-class: canonical\ntype: product\ntitle: WayCam\n---\n\n"
                          "# WayCam\n\n## What it is\n\nTurns a phone into a webcam.\n\n"
                          "## Who it serves\n\nPeople with a spare phone.\n\nFree to use while it builds traction.\n")
        self.write(bundle.root / "products/waycam/pricing.md",
                   "---\ntype: product\nx-okfdocs-class: canonical\ntitle: WayCam pricing\ndescription: Free.\n---\n\n# Pricing\n")
        before = page.read_text(encoding="utf-8")
        rel = okf.relpath(page, root)
        self.assertIn((rel, "okf", "error", "index-page"),
                      {(f.path, f.level, f.severity, f.code) for f in self.findings(root)})
        self.assertNotIn((rel, "index-frontmatter"), {(f.path, f.code) for f in self.findings(root)})
        self.cli("check", "--fix", cwd=root)
        self.cli("index", "--write", cwd=root)
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("move it to waycam/waycam.md", out)
        self.assertEqual(page.read_text(encoding="utf-8"), before)

    def test_context_reports_v3_rules_in_the_project(self):
        root = self.fixture("legacy")
        self.write(root / ".claude/skills/okf-company-brain.md", "# okf-company-brain\n")
        self.write(root / "CLAUDE.md", "Brain files: no `status` field; every file has credibility.\n")
        out = self.cli("context", cwd=root).stdout
        self.assertIn("LEGACY_RULES", out)
        self.assertIn(".claude/skills/okf-company-brain.md", out)
        self.assertIn("CLAUDE.md", out)
        self.assertNotIn("LEGACY_RULES", self.cli("context", cwd=self.fixture("repo")).stdout)


@unittest.skipUnless(HAS_GIT, "git not installed")
class TestGit(Base):
    def init_repo(self, root):
        self.git(root, "init", "-q")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-q", "-m", "init", date="2026-10-01T00:00:00Z")
        return self.git(root, "rev-parse", "HEAD")

    def change_job(self, root, date=None):
        job = root / "src/export/job.ts"
        job.write_text(job.read_text(encoding="utf-8") + "// stream large exports\n", encoding="utf-8")
        if date:
            self.git(root, "commit", "-qam", "stream exports", date=date)

    def queue(self, root):
        project = self.project(root)
        return {q["path"]: q for q in okf.stale_queue(project, self.ctx(project))}

    def test_source_committed_after_check(self):
        root = self.fixture("repo")
        self.init_repo(root)
        self.change_job(root, date="2026-11-10T00:00:00Z")
        queue = self.queue(root)
        entry = queue["docs/product/data-export.md"]
        self.assertTrue(entry["hard"])
        self.assertTrue(any("src/export/job.ts" in r for r in entry["reasons"]))
        self.assertIn("docs/system/architecture.md", queue)
        self.assertNotIn("docs/decisions/002-json-export.md", queue)

    def test_same_commit_as_doc_is_not_stale(self):
        root = self.fixture("repo")
        self.init_repo(root)
        self.change_job(root)
        doc = root / "docs/product/data-export.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("emails a download link", "emails a download link (streamed)"), encoding="utf-8")
        self.git(root, "commit", "-qam", "both", date="2026-11-10T00:00:00Z")
        queue = self.queue(root)
        self.assertNotIn("docs/product/data-export.md", queue)
        self.assertIn("docs/system/architecture.md", queue)

    def test_uncommitted_source_change(self):
        root = self.fixture("repo")
        self.init_repo(root)
        self.change_job(root)
        self.assertIn("docs/product/data-export.md", self.queue(root))

    def test_changes_since_ref(self):
        root = self.fixture("repo")
        base = self.init_repo(root)
        self.change_job(root, date="2026-11-10T00:00:00Z")
        (root / "src/new").mkdir()
        (root / "src/new/thing.ts").write_text("export const x = 1;\n", encoding="utf-8")
        (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
        project = self.project(root)
        res = okf.changes_since(project, self.ctx(project), base)
        self.assertEqual({a["path"] for a in res["affected"]},
                         {"docs/product/data-export.md", "docs/system/architecture.md"})
        self.assertEqual(res["uncovered"], ["src/new/thing.ts"])
        self.assertEqual(res["commits"], 1)
        self.assertEqual(okf.changes_since(project, self.ctx(project), "nope")["error"], "unknown git ref: nope")

    def test_last_sync_drives_context_and_stale(self):
        root = self.fixture("repo")
        base = self.init_repo(root)
        okf.add_log_entry(root / "docs", "Sync", "Synced to %s: export docs." % base[:7], today="2026-11-05")
        self.git(root, "commit", "-qam", "log sync", date="2026-11-05T00:00:00Z")
        self.change_job(root, date="2026-11-10T00:00:00Z")
        self.assertEqual(okf.last_sync_ref(self.project(root)), base[:7])
        out = self.cli("context", cwd=root).stdout
        self.assertIn("SYNC: 2 commits since the last sync", out)
        self.assertIn("GIT branch=main uncommitted=0 last_sync=%s commits_since=2" % base[:7], out)
        out = self.cli("stale", cwd=root).stdout
        self.assertIn("affected  docs/product/data-export.md  (src/export/job.ts)", out)


class TestDecay(Base):
    def test_half_life_and_stale_after(self):
        root = self.fixture("brain-repo")
        project = self.project(root)
        later = {q["path"]: q for q in okf.stale_queue(project, self.ctx(project, dt.datetime(2027, 12, 1, tzinfo=UTC)))}
        self.assertTrue(later["brain/observations/2026-06-01-exports-too-slow.md"]["delete_candidate"])
        self.assertTrue(later["brain/observations/2026-10-15-teams-want-sso.md"]["hard"])
        org = later["brain/company/organization.md"]
        self.assertFalse(org["hard"])
        self.assertIn("past half-life", org["reasons"][0])
        self.assertNotIn("brain/assets/2026-05-28-customer-call-globex.md", later)  # assets don't decay
        now = {q["path"] for q in okf.stale_queue(project, self.ctx(project))}
        self.assertEqual(now, {"brain/observations/2026-06-01-exports-too-slow.md"})

    def test_find_ranks_by_fit_and_trust(self):
        root = self.fixture("repo")
        project = self.project(root)
        res = okf.rank(project, self.ctx(project), "export limit")
        paths = [r["path"] for r in res]
        self.assertEqual(paths[0], "docs/product/data-export.md")
        self.assertLess(paths.index("docs/decisions/002-json-export.md"),
                        paths.index("docs/decisions/001-csv-first.md"))
        self.assertIn("deprecated", res[paths.index("docs/decisions/001-csv-first.md")]["flags"])


class TestHook(Base):
    def hook(self, root, file_path, session="s1"):
        payload = json.dumps({"session_id": session, "cwd": str(root), "hook_event_name": "PostToolUse",
                              "tool_name": "Edit", "tool_input": {"file_path": str(file_path)}})
        r = self.cli("hook", "--state", str(self.tmp / "state"), cwd=root, stdin=payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PostToolUse")
        return out["additionalContext"]

    def test_code_edit_reminds_once_per_session(self):
        root = self.fixture("repo")
        msg = self.hook(root, root / "src/export/job.ts")
        self.assertIn("docs/product/data-export.md", msg)
        self.assertIn("docs/system/architecture.md", msg)
        self.assertIsNone(self.hook(root, root / "src/export/job.ts"))
        self.assertIsNotNone(self.hook(root, root / "src/export/job.ts", session="s2"))
        self.assertIsNone(self.hook(root, root / "src/auth/session.ts"))  # no doc cites it

    def test_doc_edit_reports_problems(self):
        root = self.fixture("repo")
        doc = root / "docs/product/data-export.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace("(../system/architecture.md)", "(../system/gone.md)")
                       + "\nThis seamless feature is robust.\n", encoding="utf-8")
        msg = self.hook(root, doc)
        self.assertIn("link-broken", msg)
        self.assertIn("seamless", msg)
        self.assertIsNone(self.hook(root, root / "docs/index.md"))
        self.assertIsNone(self.hook(root, root / "docs/decisions/002-json-export.md"))  # clean file

    def test_silent_without_config_or_when_off(self):
        legacy = self.fixture("legacy")
        self.assertIsNone(self.hook(legacy, legacy / "src/billing/invoice.py"))
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("edits: true", "edits: false"), encoding="utf-8")
        self.assertIsNone(self.hook(root, root / "src/export/job.ts"))

    def test_enabled_is_the_old_name_for_edits(self):
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("edits: true", "enabled: true"), encoding="utf-8")
        self.assertIsNotNone(self.hook(root, root / "src/export/job.ts"))

    def session_start(self, cwd):
        r = self.cli("session-start", cwd=cwd, stdin=json.dumps({"hook_event_name": "SessionStart",
                                                                  "source": "startup", "cwd": str(cwd)}))
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        return out["additionalContext"]

    def test_session_start_names_the_bundles(self):
        root = self.fixture("repo")
        msg = self.session_start(root / "src")  # from a subfolder too
        self.assertIn("docs/ (docs)", msg)
        self.assertIn("help/ (site)", msg)
        self.assertIn("okf-docs skill", msg)
        self.assertLess(len(msg.split()), 90)

    def test_session_start_is_silent_without_config_or_when_off(self):
        self.assertIsNone(self.session_start(self.fixture("legacy")))
        self.assertIsNone(self.session_start(self.fixture("app") if (FIXTURES / "app").is_dir() else self.tmp))
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("hooks:\n", "hooks:\n  session: false\n", 1), encoding="utf-8")
        self.assertIsNone(self.session_start(root))
        self.assertIn("HOOKS session=off edits=on", self.cli("context", cwd=root).stdout)

    def test_bad_input_is_silent(self):
        for stdin in ("", "not json", "[]", '{"tool_input": "x"}', '{"tool_input": {"file_path": 3}}'):
            r = self.cli("hook", stdin=stdin)
            self.assertEqual((r.returncode, r.stdout), (0, ""), stdin)


class TestCLI(Base):
    def test_project_flag_in_either_position(self):
        root = self.fixture("legacy")
        for args in (("--project", str(root), "check"), ("check", "--project", str(root))):
            res = self.cli(*args)
            self.assertEqual(res.returncode, 1, res.stderr)  # the legacy fixture has OKF errors
            self.assertIn("OKF errors", res.stdout)

    def test_help_and_version(self):
        self.assertIn("okf-docs 1.0.5", self.cli("--version").stdout)
        self.assertEqual(self.cli().returncode, 2)
        out = self.cli("--help").stdout
        for cmd in ("context", "check", "index", "lint", "stale", "find", "log", "now", "upgrade", "hook",
                    "session-start"):
            self.assertIn(cmd, out)

    def test_context(self):
        r = self.cli("context", cwd=self.fixture("repo"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("CONFIG .okf/config.yaml · modules: core, code, publish", out)
        self.assertIn("BUNDLE docs/ kind=docs preset=service files=4 drafts=0 unverified=1 okf_errors=0", out)
        self.assertIn("BUNDLE help/ kind=site preset=help-center files=1 drafts=0 unverified=1", out)
        self.assertIn("ACTOR human:tester (from OKF_ACTOR) · agent okf-docs/1.0.5", out)
        self.assertIn("MODULES_OFF: brain", out)
        self.assertNotIn("LEGACY_SKILLS", out)
        self.assertRegex(out, r"NOW \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d")

    def test_context_without_config(self):
        out = self.cli("context", cwd=self.fixture("legacy")).stdout
        self.assertIn("NO_CONFIG", out)
        self.assertIn("OKF bundles found: docs/", out)
        self.assertIn("UPGRADE: 2 files", out)

    def test_context_tells_unrunnable_git_from_no_git(self):
        root = self.fixture("repo")
        self.assertIn("GIT none", self.cli("context", cwd=root).stdout)
        self.assertIn("can't compare with HEAD~3: not a git repository",
                      self.cli("stale", "--since", "HEAD~3", cwd=root).stdout)
        (root / ".git").mkdir()  # a repository git can't read, as when a sandbox blocks git
        out = self.cli("context", cwd=root).stdout
        self.assertIn("GIT unavailable", out)
        self.assertIn("GIT_UNAVAILABLE: this is a git repository", out)
        self.assertIn("can't compare with HEAD~3: git didn't run here",
                      self.cli("stale", "--since", "HEAD~3", cwd=root).stdout)

    def test_context_flags_old_skills(self):
        synced = self.home / ".claude/skills/synced/abc/okf-company-brain"
        synced.mkdir(parents=True)
        (synced / "SKILL.md").write_text("---\nname: okf-company-brain\n---\n", encoding="utf-8")
        local = self.home / ".claude/skills/okf-docs"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("---\nname: okf-docs\n---\n", encoding="utf-8")
        out = self.cli("context", cwd=self.fixture("repo")).stdout
        self.assertIn("okf-company-brain (synced from claude.ai", out)
        self.assertIn("okf-docs (local copy: delete ~/.claude/skills/okf-docs)", out)

    def test_check_json_and_exit_codes(self):
        root = self.fixture("repo")
        r = self.cli("check", "--json", cwd=root)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.loads(r.stdout)["summary"]["okf_errors"], 0)
        (root / "docs/product/broken.md").write_text("---\ntype: concept\ntitle: Broken\n\nno closing line\n",
                                                     encoding="utf-8")
        r = self.cli("check", "docs/product/broken.md", cwd=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fm-unterminated", r.stdout)

    def test_now_and_log(self):
        root = self.fixture("repo")
        out = self.cli("now", cwd=root).stdout
        self.assertIn("human: human:tester", out)
        self.assertIn("agent: okf-docs/1.0.5", out)
        r = self.cli("log", "docs", "Update", "Changed", "data-export.md.", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("* **Update**: Changed data-export.md.", (root / "docs/log.md").read_text(encoding="utf-8"))

    def test_lint_and_find_output(self):
        root = self.fixture("repo")
        out = self.cli("lint", "docs", cwd=root).stdout
        self.assertIn("data-export.md", out)
        out = self.cli("find", "export", "--json", cwd=root).stdout
        self.assertTrue(json.loads(out))


class TestOKF03(Base):
    """OKF 0.3 behavior: extension keys, root index frontmatter, timestamps, current-event trust, actors,
    concepts and reserved files, lifecycle, paths, values, sources, Attested Computations and the 0.2 upgrade."""

    DATA = "docs/product/data-export.md"

    def edit(self, path, old, new, count=1):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, count), encoding="utf-8")

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, root, path):
        return {f.code for f in self.findings(root) if f.path == path}

    def found(self, root, path, code):
        return [f for f in self.findings(root) if f.path == path and f.code == code]

    def doc(self, root, rel):
        project = self.project(root)
        return okf.Doc.load(project.bundle_for(root / rel), root / rel)

    def test_versions(self):
        self.assertEqual((okf.OKF_VERSION, okf.VERSION), ("0.3", "1.0.5"))
        self.assertEqual(okf.AGENT_ACTOR, "okf-docs/1.0.5")

    # D2 ---------------------------------------------------------------------
    def test_new_key_names_are_read_and_old_names_still_work(self):
        root = self.fixture("repo")
        doc = self.doc(root, self.DATA)
        self.assertEqual((doc.visibility, doc.ext("specificity")), ("public", "specific"))
        self.assertNotIn("legacy-key-name", self.codes(root, self.DATA))
        self.edit(root / self.DATA, "x-okfdocs-visibility: public", "visibility: public")
        self.assertEqual(self.doc(root, self.DATA).visibility, "public")  # the old name is a fallback
        found = self.found(root, self.DATA, "legacy-key-name")
        self.assertEqual(len(found), 1)
        self.assertIn("`visibility` is the 0.9 name; write `x-okfdocs-visibility`", found[0].message)
        self.assertEqual((found[0].level, found[0].severity, found[0].fixable), ("house", "warn", "upgrade"))
        self.edit(root / self.DATA, "visibility: public", "visibility: public\nx-okfdocs-visibility: internal")
        self.assertEqual(self.doc(root, self.DATA).visibility, "internal")  # both set: the new one wins
        self.assertIn("are both set", self.found(root, self.DATA, "legacy-key-name")[0].message)

    def test_enum_values_apply_to_both_names(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "x-okfdocs-specificity: specific", "specificity: huge")
        self.assertIn("enum-value", self.codes(root, self.DATA))
        self.edit(root / self.DATA, "specificity: huge", "x-okfdocs-specificity: huge")
        msg = self.found(root, self.DATA, "enum-value")[0].message
        self.assertIn("`x-okfdocs-specificity`", msg)

    def test_upgrade_renames_old_keys_in_place(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "x-okfdocs-specificity: specific", "specificity: specific")
        self.edit(root / self.DATA, "x-okfdocs-visibility: public", "visibility: public")
        cfg = root / ".okf/config.yaml"
        before_cfg = cfg.read_text(encoding="utf-8")
        keys_before = list(self.doc(root, self.DATA).fm)
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("renamed `specificity` → `x-okfdocs-specificity`", out)
        self.assertIn("renamed `visibility` → `x-okfdocs-visibility`", out)
        doc = self.doc(root, self.DATA)
        self.assertEqual([k.replace("x-okfdocs-", "") for k in doc.fm], keys_before)  # same positions
        self.assertEqual((doc.fm["x-okfdocs-specificity"], doc.fm["x-okfdocs-visibility"]), ("specific", "public"))
        self.assertNotIn("legacy-key-name", self.codes(root, self.DATA))
        self.assertEqual(cfg.read_text(encoding="utf-8"), before_cfg)  # config keys are not frontmatter
        self.assertIn("changed 0 files", self.cli("upgrade", cwd=root).stdout)

    def test_upgrade_drops_an_old_key_when_the_new_one_is_set(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "x-okfdocs-visibility: public", "visibility: internal\nx-okfdocs-visibility: public")
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("removed `visibility`", out)
        self.assertEqual(self.doc(root, self.DATA).visibility, "public")
        self.assertNotIn("\nvisibility:", (root / self.DATA).read_text(encoding="utf-8"))

    def test_v3_credibility_verified_under_either_name(self):
        root = self.fixture("repo")
        page = root / "help/export-your-data.md"
        for key in ("credibility", "x-okfdocs-credibility"):
            page.write_text(page.read_text(encoding="utf-8")
                            .replace("visibility: public\n", "visibility: public\n%s: verified\n" % key, 1), encoding="utf-8")
            self.assertIn("credibility-verified", self.codes(root, "help/export-your-data.md"), key)
            self.edit(page, "%s: verified\n" % key, "")

    # D3 ---------------------------------------------------------------------
    def test_root_index_frontmatter_is_valid_and_kept(self):
        root = self.fixture("repo")
        self.assertFalse([f for f in self.findings(root) if f.path == "docs/index.md" and f.severity != "info"])
        idx = root / "docs/index.md"
        self.edit(idx, "---\n\n", "license: CC-BY-4.0\nx-okfdocs-note: keep me\n---\n\n")
        self.assertFalse([f for f in self.findings(root) if f.path == "docs/index.md" and f.severity != "info"])
        self.write(root / "docs/product/data-import.md", IMPORT_DOC)
        self.assertIn("index-stale", self.codes(root, "docs/product/index.md"))
        self.assertEqual(self.cli("check", "--fix", cwd=root).returncode, 0)
        text = idx.read_text(encoding="utf-8")
        for line in ('okf_version: "0.3"', "title: Acme API docs", "description: How the Acme API works",
                     "license: CC-BY-4.0", "x-okfdocs-note: keep me"):
            self.assertIn(line, text)
        self.write(root / "docs/product/data-import-two.md", IMPORT_DOC.replace("Data import", "Data import two"))
        self.assertEqual(self.cli("index", "--write", cwd=root).returncode, 0)
        self.assertIn("license: CC-BY-4.0", idx.read_text(encoding="utf-8"))
        self.assertIn("Data import two", (root / "docs/product/index.md").read_text(encoding="utf-8"))

    def test_only_an_index_below_the_root_with_frontmatter_is_an_error(self):
        root = self.fixture("repo")
        self.write(root / "docs/product/index.md", "---\ntitle: Product\n---\n\n# Concepts\n\n"
                   "* [Data export](data-export.md) - Export a workspace as CSV or JSON; runs as a background job "
                   "with a 500 MB limit.\n")
        found = self.found(root, "docs/product/index.md", "index-frontmatter")
        self.assertEqual([(f.level, f.severity) for f in found], [("okf", "error")])
        self.cli("check", "--fix", cwd=root)
        self.assertFalse((root / "docs/product/index.md").read_text(encoding="utf-8").startswith("---"))

    def test_root_index_meta_and_okf_version_findings(self):
        root = self.fixture("repo")
        idx = root / "docs/index.md"
        self.write(idx, idx.read_text(encoding="utf-8").replace("title: Acme API docs\n", ""))
        found = self.found(root, "docs/index.md", "root-index-meta")
        self.assertEqual([(f.level, f.severity) for f in found], [("house", "info")])
        self.edit(idx, 'okf_version: "0.3"', "okf_version: 0.3")  # an unquoted number
        self.assertIn("yaml-quote", self.codes(root, "docs/index.md"))
        self.cli("check", "--fix", cwd=root)
        text = idx.read_text(encoding="utf-8")
        self.assertIn('okf_version: "0.3"', text)
        self.assertIn("description: How the Acme API works", text)
        self.assertNotIn("yaml-quote", self.codes(root, "docs/index.md"))

    def test_older_bundle_gets_one_fixable_okf_version_warning(self):
        root = self.fixture("repo")
        idx = root / "docs/index.md"
        self.edit(idx, 'okf_version: "0.3"', 'okf_version: "0.2"')
        found = self.found(root, "docs/index.md", "okf-version")
        self.assertEqual([(f.level, f.severity, f.fixable) for f in found], [("okf", "warn", "fix")])
        self.cli("check", "--fix", cwd=root)
        self.assertIn('okf_version: "0.3"', idx.read_text(encoding="utf-8"))
        self.assertIn("title: Acme API docs", idx.read_text(encoding="utf-8"))
        idx.write_text(idx.read_text(encoding="utf-8").replace("okf_version", "okf_other", 1), encoding="utf-8")
        self.assertEqual(len(self.found(root, "docs/index.md", "okf-version")), 1)  # no version: also an older bundle

    def test_upgrade_keeps_root_title_and_drops_v3_keys(self):
        root = self.fixture("repo")
        idx = root / "docs/index.md"
        self.edit(idx, 'okf_version: "0.3"', 'okf_version: "0.2"\ntype: index\nlicense: MIT\nscope: acme\nx-okfdocs-note: hi')
        self.assertIn("index-frontmatter", self.codes(root, "docs/index.md"))
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("dropped root index key `type`", out)
        self.assertIn("dropped root index key `scope`", out)
        text = idx.read_text(encoding="utf-8")
        self.assertIn('okf_version: "0.3"', text)
        for kept in ("title: Acme API docs", "description:", "license: MIT", "x-okfdocs-note: hi"):
            self.assertIn(kept, text)
        self.assertNotIn("type: index", text)
        self.assertNotIn("scope: acme", text)
        self.assertNotIn("index-frontmatter", self.codes(root, "docs/index.md"))

    # D4 ---------------------------------------------------------------------
    def test_date_only_timestamps(self):
        root = self.fixture("repo")
        base = self.codes(root, self.DATA)
        self.edit(root / self.DATA, "at: 2026-11-01T10:00:00+01:00", "at: 2026-11-01")
        self.edit(root / self.DATA, "sources:\n", "stale_after: 2027-02-01\nsources:\n")
        self.edit(root / self.DATA, "  - id: job\n", "  - id: job\n    last_modified: 2026-10-30\n")
        found = self.findings(root)
        mine = [f for f in found if f.path == self.DATA]
        self.assertEqual({f.code for f in mine} - base, {"timestamp-date-only"})
        f = [x for x in mine if x.code == "timestamp-date-only"][0]
        self.assertEqual((f.level, f.severity, f.fixable), ("house", "warn", "upgrade"))
        self.assertIn("generated.at", f.message)
        self.assertEqual(okf.parse_ts("2027-02-01")[0], dt.datetime(2027, 2, 1, tzinfo=UTC))
        self.cli("upgrade", cwd=root)
        text = (root / self.DATA).read_text(encoding="utf-8")
        self.assertIn("at: 2026-11-01T00:00:00Z", text)
        self.assertIn("stale_after: 2027-02-01\n", text)  # valid OKF: left as written
        self.assertIn("last_modified: 2026-10-30\n", text)

    def test_quoted_and_unquoted_timestamps_are_the_same(self):
        for text in ('"2026-11-01T10:00:00+01:00"', "2026-11-01T10:00:00+01:00"):
            data, _ = okf.yaml_load("at: %s\n" % text)
            self.assertEqual(okf.parse_ts(data["at"])[1], None)
        self.assertEqual(okf.parse_ts("2026-11-01T10:00:00")[1], okf.NO_OFFSET)  # still invalid

    # D5 ---------------------------------------------------------------------
    def test_only_current_events_count_for_trust(self):
        root = self.fixture("repo")
        self.assertEqual(self.doc(root, self.DATA).trust(), "human-reviewed")
        self.edit(root / self.DATA, "at: 2026-11-01T10:00:00+01:00", "at: 2026-11-05T12:00:00Z")  # generated.at moves
        doc = self.doc(root, self.DATA)
        self.assertEqual(len(doc.verified_entries()), 1)  # the history stays in the file
        self.assertEqual(doc.current_events(), [])
        self.assertEqual((doc.trust(), doc.reviewed(), doc.trust_note()), ("unverified", False,
                                                                           "verified before the last change"))
        self.assertEqual(doc.last_check(), dt.datetime(2026, 11, 5, 12, tzinfo=UTC))
        codes = self.codes(root, self.DATA)
        self.assertIn("verification-outdated", codes)
        self.assertNotIn("unverified", codes)
        f = self.found(root, self.DATA, "verification-outdated")[0]
        self.assertEqual((f.level, f.severity), ("content", "info"))
        self.assertIn("verified before the last change on 2026-11-05; re-check it", f.message)
        project = self.project(root)
        res = {r["path"]: r for r in okf.rank(project, self.ctx(project), "export")}
        self.assertEqual(res[self.DATA]["trust_note"], "verified before the last change")
        self.assertIn("verified before the last change", self.cli("find", "export", cwd=root).stdout)
        s = json.loads(self.cli("check", "--json", cwd=root).stdout)["summary"]
        self.assertEqual(s["outdated"], 1)
        self.assertIn("verified before the last change", self.cli("check", cwd=root).stdout)

    def test_current_events_after_a_change_restore_trust(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "at: 2026-11-01T10:00:00+01:00", "at: 2026-11-05T12:00:00Z")
        self.edit(root / self.DATA, "verified:\n", "verified:\n  - by: okf-docs/1.0.5\n    at: 2026-11-06T09:00:00Z\n")
        doc = self.doc(root, self.DATA)
        self.assertEqual((doc.trust(), len(doc.current_events())), ("machine-confirmed", 1))
        self.assertEqual(doc.last_check(), dt.datetime(2026, 11, 6, 9, tzinfo=UTC))
        self.edit(root / self.DATA, "verified:\n", "verified:\n  - by: human:sam\n    at: 2026-11-07T09:00:00Z\n")
        self.assertEqual(self.doc(root, self.DATA).trust(), "human-reviewed")
        self.assertNotIn("verification-outdated", self.codes(root, self.DATA))

    def test_events_count_when_generated_is_absent(self):
        root = self.fixture("repo")
        text = (root / self.DATA).read_text(encoding="utf-8")
        self.write(root / self.DATA, text.replace("generated:\n  by: okf-docs/1.0.5\n  at: 2026-11-01T10:00:00+01:00\n", ""))
        doc = self.doc(root, self.DATA)
        self.assertEqual((doc.trust(), doc.last_check()), ("human-reviewed", dt.datetime(2026, 11, 2, 8, tzinfo=UTC)))

    def test_decay_counts_from_the_last_check(self):
        root = self.fixture("brain-repo")
        doc = self.doc(root, "brain/company/organization.md")
        self.assertEqual(doc.last_check(), dt.datetime(2026, 10, 1, 8, tzinfo=UTC))
        self.edit(root / "brain/company/organization.md", "at: 2026-10-01T09:00:00+02:00", "at: 2026-10-05T09:00:00+02:00")
        self.assertEqual(self.doc(root, "brain/company/organization.md").last_check(),
                         dt.datetime(2026, 10, 5, 7, tzinfo=UTC))  # generated.at: the event is history

    # D6 ---------------------------------------------------------------------
    def test_actors(self):
        for good in ("human:alex", "team:finance", "process:nightly", "okf-docs/1.0.5", "bot:ci-7"):
            self.assertTrue(okf.ACTOR_RE.match(good), good)
        for bad in ("alex", "Alex Smith", "agent", "team: finance"):
            self.assertFalse(okf.ACTOR_RE.match(bad), bad)
        root = self.fixture("repo")
        self.edit(root / self.DATA, "by: human:alex\n    at: 2026-11-02T09:00:00+01:00", "by: team:finance\n    at: 2026-11-02T09:00:00+01:00")
        doc = self.doc(root, self.DATA)
        self.assertEqual(doc.trust(), "machine-confirmed")  # only human: is human-reviewed
        self.assertNotIn("actor-format", self.codes(root, self.DATA))

    def test_source_author_is_an_actor(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "  - id: job\n", "  - id: job\n    author: team:platform\n")
        self.assertNotIn("actor-format", self.codes(root, self.DATA))
        self.edit(root / self.DATA, "author: team:platform", "author: Platform Team")
        found = self.found(root, self.DATA, "actor-format")
        self.assertEqual(len(found), 1)
        self.assertIn("sources[0].author", found[0].message)

    # D7 ---------------------------------------------------------------------
    def test_log_frontmatter_is_an_error_and_fixable(self):
        root = self.fixture("repo")
        log = root / "docs/log.md"
        log.write_text("---\ntitle: Log\n---\n\n" + log.read_text(encoding="utf-8"), encoding="utf-8")
        found = self.found(root, "docs/log.md", "log-frontmatter")
        self.assertEqual([(f.level, f.severity, f.fixable) for f in found], [("okf", "error", "fix")])
        r = self.cli("check", cwd=root)
        self.assertEqual(r.returncode, 1)
        r = self.cli("check", "--fix", cwd=root)
        self.assertIn("fixed  docs/log.md", r.stdout)
        text = log.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Directory Update Log\n"), text)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("log-frontmatter", self.codes(root, "docs/log.md"))
        self.assertIn("## 2026-11-02", text)

    def test_log_headings_and_order(self):
        root = self.fixture("repo")
        log = root / "docs/log.md"
        log.write_text(log.read_text(encoding="utf-8") + "\n## Notes\n\n* **Update**: x.\n\n## 2026-12-01\n", encoding="utf-8")
        found = {f.code: f for f in self.findings(root) if f.path == "docs/log.md"}
        self.assertEqual((found["log-format"].level, found["log-format"].severity), ("okf", "error"))
        self.assertEqual((found["log-order"].level, found["log-order"].severity), ("okf", "warn"))

    def test_index_and_log_are_never_concepts(self):
        root = self.fixture("repo")
        project = self.project(root)
        self.assertFalse([d for d in project.bundles[0].docs if d.path.name in ("index.md", "log.md")])
        self.write(root / "docs/product/index.md", "---\ntype: concept\ntitle: X\n---\n\n# X\n\n* [Data export](data-export.md)\n")
        self.assertNotIn("docs/product/index.md", {d.prel for d in self.project(root).bundles[0].docs})

    # D8 ---------------------------------------------------------------------
    def test_duplicate_keys_are_an_okf_error(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "title: Data export\n", "title: Data export\ntitle: Export\n")
        found = self.found(root, self.DATA, "duplicate-key")
        self.assertEqual([(f.level, f.severity) for f in found], [("okf", "error")])
        self.assertIn("title", found[0].message)
        self.assertNotIn("yaml-strict", self.codes(root, self.DATA))
        self.assertEqual(self.cli("check", cwd=root).returncode, 1)

    def test_only_conformance_breaks_are_errors(self):
        root = self.fixture("legacy")
        errors = {(f.path, f.code) for f in self.findings(root) if f.severity == "error"}
        self.assertEqual(errors, {("docs/product/index.md", "index-frontmatter")})

    # D9 ---------------------------------------------------------------------
    def test_unknown_status_is_not_current(self):
        root = self.fixture("repo")
        self.assertEqual(self.doc(root, self.DATA).current, True)
        project = self.project(root)
        stable = {r["path"]: r for r in okf.rank(project, self.ctx(project), "export")}[self.DATA]
        self.edit(root / self.DATA, "tags: [export, jobs]\n", "tags: [export, jobs]\nstatus: archived\n")
        doc = self.doc(root, self.DATA)
        self.assertFalse(doc.current)
        self.assertEqual(doc.status, "archived")  # the value is kept
        f = self.found(root, self.DATA, "status-value")
        self.assertEqual([(x.level, x.severity) for x in f], [("okf", "warn")])
        project = self.project(root)
        ranked = {r["path"]: r for r in okf.rank(project, self.ctx(project), "export")}[self.DATA]
        self.assertIn("not-current", ranked["flags"])
        self.assertLess(ranked["score"], stable["score"] * 0.5)
        shown = {r["path"]: r for r in okf.rank(project, self.ctx(project), "export", include_all=True)}[self.DATA]
        self.assertGreater(shown["score"], ranked["score"])
        self.assertNotIn("unverified", self.codes(root, self.DATA))

    def test_superseded_by_needs_deprecated(self):
        root = self.fixture("repo")
        self.assertNotIn("superseded-not-deprecated", {f.code for f in self.findings(root)})
        self.edit(root / self.DATA, "tags: [export, jobs]\n", "tags: [export, jobs]\nsuperseded_by: ../system/architecture.md\n")
        found = self.found(root, self.DATA, "superseded-not-deprecated")
        self.assertEqual([(f.level, f.severity) for f in found], [("okf", "warn")])
        self.edit(root / self.DATA, "superseded_by:", "status: deprecated\nsuperseded_by:")
        self.assertNotIn("superseded-not-deprecated", self.codes(root, self.DATA))

    def test_promoted_observation_is_deprecated_in_the_fixture(self):
        root = self.fixture("brain-repo")
        doc = self.doc(root, "brain/observations/2026-10-15-teams-want-sso.md")
        self.assertEqual((doc.status, doc.get("superseded_by")), ("deprecated", "../market/audiences.md"))
        self.assertNotIn("superseded-not-deprecated", {f.code for f in self.findings(root)})

    def test_unparsable_stale_after_counts_as_stale(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "tags:", "stale_after: soon\ntags:")
        doc = self.doc(root, self.DATA)
        self.assertTrue(doc.is_stale(AT))
        codes = self.codes(root, self.DATA)
        self.assertIn("stale-after-format", codes)
        self.assertIn("stale", codes)
        project = self.project(root)
        entry = {q["path"]: q for q in okf.stale_queue(project, self.ctx(project))}[self.DATA]
        self.assertTrue(entry["hard"])
        self.assertIn("valid timestamp", entry["reasons"][0])
        ranked = {r["path"]: r for r in okf.rank(project, self.ctx(project), "export")}[self.DATA]
        self.assertIn("stale", ranked["flags"])

    def test_empty_stale_after_is_absent_and_dates_work(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "tags:", "stale_after:\ntags:")
        self.assertFalse(self.doc(root, self.DATA).is_stale(AT))
        self.assertNotIn("stale-after-format", self.codes(root, self.DATA))
        self.edit(root / self.DATA, "stale_after:\n", 'stale_after: "2026-06-01"\n')
        self.assertTrue(self.doc(root, self.DATA).is_stale(AT))
        self.assertNotIn("stale-after-format", self.codes(root, self.DATA))
        self.edit(root / self.DATA, 'stale_after: "2026-06-01"', "stale_after: 2027-01-01")
        self.assertFalse(self.doc(root, self.DATA).is_stale(AT))

    # D10 --------------------------------------------------------------------
    def bare_root_path(self, root):
        self.edit(root / self.DATA, "resource: ../decisions/002-json-export.md", "resource: decisions/002-json-export.md")

    def test_path_root_fallback_in_a_02_bundle(self):
        root = self.fixture("repo")
        self.edit(root / "docs/index.md", 'okf_version: "0.3"', 'okf_version: "0.2"')
        self.bare_root_path(root)
        found = self.found(root, self.DATA, "path-root-fallback")
        self.assertEqual([(f.level, f.severity, f.fixable) for f in found], [("okf", "warn", "upgrade")])
        self.assertIn("write it as /decisions/002-json-export.md", found[0].message)
        self.assertNotIn("source-missing", self.codes(root, self.DATA))
        # check --fix does not move a bundle to 0.3 while it still relies on the fallback
        self.cli("check", "--fix", cwd=root)
        self.assertIn('okf_version: "0.2"', (root / "docs/index.md").read_text(encoding="utf-8"))
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("path-root-fallback", out)
        self.assertIn("resource: ../decisions/002-json-export.md", (root / self.DATA).read_text(encoding="utf-8"))
        self.assertIn('okf_version: "0.3"', (root / "docs/index.md").read_text(encoding="utf-8"))
        self.assertNotIn("path-root-fallback", {f.code for f in self.findings(root)})

    def test_rooted_link_style_rewrites_to_a_leading_slash(self):
        root = self.fixture("repo")
        self.edit(root / "docs/index.md", 'okf_version: "0.3"', 'okf_version: "0.2"')
        self.edit(root / ".okf/config.yaml", "links: relative", "links: rooted")
        self.bare_root_path(root)
        self.cli("upgrade", cwd=root)
        self.assertIn("resource: /decisions/002-json-export.md", (root / self.DATA).read_text(encoding="utf-8"))

    def test_no_fallback_in_a_03_bundle(self):
        root = self.fixture("repo")
        self.bare_root_path(root)
        codes = self.codes(root, self.DATA)
        self.assertNotIn("path-root-fallback", codes)
        self.assertIn("source-path", codes)  # it doesn't resolve: the 0.3 rule has no fallback
        self.edit(root / self.DATA, "resource: decisions/002-json-export.md", "resource: /decisions/002-json-export.md")
        self.assertFalse({"source-path", "source-missing", "path-root-fallback"} & self.codes(root, self.DATA))

    def test_sources_outside_the_bundle_are_still_read(self):
        root = self.fixture("repo")
        doc = self.doc(root, self.DATA)
        self.assertIn(root / "src/export/job.ts", [p for _, p in doc.local_sources()])

    def test_percent_encoded_paths_resolve(self):
        root = self.fixture("repo")
        self.write(root / "docs/product/data import.md", IMPORT_DOC)
        doc = self.doc(root, self.DATA)
        self.assertEqual(doc.resolve("data%20import.md"), root / "docs/product/data import.md")

    # D11 --------------------------------------------------------------------
    def test_scalar_tags_warn_and_are_never_split_on_read(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "tags: [export, jobs]", "tags: export, jobs")
        doc = self.doc(root, self.DATA)
        self.assertEqual(doc.tags, ["export, jobs"])
        found = self.found(root, self.DATA, "tags-format")
        self.assertEqual([(f.level, f.severity, f.fixable) for f in found], [("house", "warn", "upgrade")])
        out = self.cli("upgrade", cwd=root).stdout
        self.assertIn("split", out)
        self.assertEqual(self.doc(root, self.DATA).tags, ["export", "jobs"])
        self.edit(root / self.DATA, "tags: [export, jobs]", "tags: export")
        self.assertIn("tags: scalar", self.cli("upgrade", cwd=root).stdout)
        self.assertEqual(self.doc(root, self.DATA).tags, ["export"])

    def test_blank_values_are_absent(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "tags: [export, jobs]", "tags:\nsources_note: ''\nstatus: ''\nsuperseded_by: []")
        codes = self.codes(root, self.DATA)
        self.assertFalse({"tags-format", "status-value", "superseded-not-deprecated"} & codes)
        self.assertEqual(self.doc(root, self.DATA).status, "stable")

    def test_numbers_and_booleans_need_quotes(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "title: Data export", "title: 2026")
        self.edit(root / self.DATA, "tags:", "status: true\ntags:")
        found = [f for f in self.found(root, self.DATA, "yaml-quote")]
        self.assertEqual(len(found), 2)
        self.assertEqual({(f.level, f.severity) for f in found}, {("okf", "warn")})

    # D12 --------------------------------------------------------------------
    def test_source_checks(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "  - id: d002\n", "  - title: no resource\n  - id: job\n    resource: ../decisions/001-csv-first.md\n"
                  "    usage_count: 40\n  - id: d002\n")
        self.edit(root / self.DATA, "## Related", "A claim.[^ghost]\n\n## Related")
        found = {}
        for f in self.findings(root):
            if f.path == self.DATA:
                found.setdefault(f.code, []).append(f)
        for code in ("source-no-resource", "source-id-duplicate", "usage-window-missing", "footnote-no-source"):
            self.assertEqual([(f.level, f.severity) for f in found[code]], [("okf", "warn")], code)
        self.assertIn("ghost", found["footnote-no-source"][0].message)
        self.assertTrue(found["footnote-no-source"][0].line)
        self.edit(root / self.DATA, "usage_count: 40", "usage_count: 40\n    usage_window:\n      from: 2026-10-01\n      to: 2026-10-31")
        self.assertNotIn("usage-window-missing", self.codes(root, self.DATA))

    def test_a_shared_usage_window_covers_usage_count(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "sources:\n", "usage_window:\n  from: 2026-10-01\n  to: 2026-10-31\nsources:\n")
        self.edit(root / self.DATA, "  - id: job\n", "  - id: job\n    usage_count: 12\n")
        self.assertNotIn("usage-window-missing", self.codes(root, self.DATA))

    # D13 --------------------------------------------------------------------
    ATTESTED = """---
type: Attested Computation
title: Weekly exports
description: Count exports per week.
runtime: postgres
parameters:
  - name: week
    type: date
attester:
  resource: attest.py
generated:
  by: okf-docs/1.0.5
  at: 2026-11-01T10:00:00+01:00
---

# Weekly exports

## Computation

```sql
select count(*) from exports;
```
"""

    def test_attested_computation_checks(self):
        root = self.fixture("repo")
        page = self.write(root / "docs/product/weekly-exports.md", self.ATTESTED)
        self.write(root / "docs/product/attest.py", "print('ok')\n")
        rel = "docs/product/weekly-exports.md"
        bad = {"attested-runtime", "attested-computation", "attested-parameters", "attested-executor"}
        self.assertFalse(bad & self.codes(root, rel))
        self.assertNotIn("attested-no-attester", self.codes(root, rel))
        self.edit(page, "runtime: postgres\n", "")
        self.edit(page, "  - name: week\n    type: date\n", "  - name: week\n")
        self.edit(page, "attester:\n  resource: attest.py\n", "executor:\n  resource: run.py\n")
        self.edit(page, "select count(*) from exports;\n```\n", "select 1;\n```\n\n```sql\nselect 2;\n```\n")
        codes = self.codes(root, rel)
        self.assertTrue(bad <= codes, codes)
        info = self.found(root, rel, "attested-no-attester")
        self.assertEqual([(f.level, f.severity) for f in info], [("okf", "info")])
        self.assertIn("not attestable", info[0].message)
        for f in self.findings(root):
            if f.path == rel and f.code.startswith("attested-") and f.code != "attested-no-attester":
                self.assertEqual((f.level, f.severity), ("okf", "warn"))
        text = page.read_text(encoding="utf-8")
        page.write_text(text.replace("---\n\n# Weekly", "computation: query.sql\n---\n\n# Weekly", 1), encoding="utf-8")
        self.assertTrue([f for f in self.found(root, rel, "attested-computation") if "don't also" in f.message])
        page.write_text(text.replace("## Computation", "## Notes").replace("---\n\n# Weekly", "---\n\n# Weekly", 1),
                        encoding="utf-8")
        self.assertTrue([f for f in self.found(root, rel, "attested-computation") if "no computation" in f.message])

    # D14 --------------------------------------------------------------------
    def make_02(self, root):
        """Rewrite the repo fixture the way okf-docs 0.9.x wrote it."""
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8").replace("okf-docs/1.0.5", "okf-docs/0.9.1")
            fm = text.split("\n---\n", 1)
            if text.startswith("---\n") and len(fm) == 2:
                head = fm[0].replace("x-okfdocs-", "")
                text = head + "\n---\n" + fm[1]
            path.write_text(text, encoding="utf-8")
        self.edit(root / "docs/index.md", 'okf_version: "0.3"', 'okf_version: "0.2"')
        self.edit(root / "help/index.md", 'okf_version: "0.3"', 'okf_version: "0.2"')
        data = root / self.DATA
        self.edit(data, "at: 2026-11-01T10:00:00+01:00", "at: 2026-11-04")  # generated.at as a date, after the review
        self.edit(data, "tags: [export, jobs]", "tags: export, jobs")
        self.edit(data, "resource: ../decisions/002-json-export.md", "resource: decisions/002-json-export.md")
        log = root / "docs/log.md"
        log.write_text("---\ntitle: Log\n---\n\n" + log.read_text(encoding="utf-8"), encoding="utf-8")

    def test_upgrade_a_02_bundle_end_to_end(self):
        root = self.fixture("repo")
        self.make_02(root)
        codes = {(f.path, f.code) for f in self.findings(root)}
        for expected in (("docs/index.md", "okf-version"), (self.DATA, "legacy-key-name"),
                         (self.DATA, "timestamp-date-only"), (self.DATA, "tags-format"),
                         (self.DATA, "path-root-fallback"), ("docs/log.md", "log-frontmatter")):
            self.assertIn(expected, codes)
        ctx_out = self.cli("context", cwd=root).stdout
        self.assertIn("UPGRADE: ", ctx_out)
        self.assertIn("an older format", ctx_out)
        dry = self.cli("upgrade", "--dry-run", cwd=root)
        self.assertIn("would change", dry.stdout)
        self.assertIn("Trust drops under OKF 0.3", dry.stdout)
        self.assertIn("docs/product/data-export.md: human-reviewed → unverified", dry.stdout)
        self.assertIn("older than generated.at", dry.stdout)
        self.assertIn("visibility:", (root / self.DATA).read_text(encoding="utf-8"))  # a dry run wrote nothing
        r = self.cli("upgrade", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in ("renamed `specificity` → `x-okfdocs-specificity`", "renamed `visibility`",
                     "generated.at: date → 2026-11-04T00:00:00Z", "path-root-fallback", "tags: split",
                     "removed the frontmatter", 'okf_version: 0.2 -> "0.3"'):
            self.assertIn(line, r.stdout)
        self.assertIn('okf_version: "0.3"', (root / "docs/index.md").read_text(encoding="utf-8"))
        self.assertIn("title: Acme API docs", (root / "docs/index.md").read_text(encoding="utf-8"))
        self.assertTrue((root / "docs/log.md").read_text(encoding="utf-8").startswith("# Directory Update Log"))
        doc = self.doc(root, self.DATA)
        self.assertEqual(doc.tags, ["export", "jobs"])
        self.assertEqual(doc.trust(), "unverified")  # the review is older than generated.at: still in the file
        self.assertEqual(len(doc.verified_entries()), 1)
        self.assertEqual(doc.fm["x-okfdocs-visibility"], "public")
        self.assertIn("decisions/002-json-export.md", (root / self.DATA).read_text(encoding="utf-8"))
        left = {(f.path, f.code) for f in self.findings(root) if f.level in ("okf", "house") and f.severity != "info"}
        self.assertEqual(left, set())
        self.assertIn("changed 0 files", self.cli("upgrade", cwd=root).stdout)
        self.assertNotIn("UPGRADE:", self.cli("context", cwd=root).stdout)

    def test_a_single_file_upgrade_leaves_the_bundle_version(self):
        root = self.fixture("repo")
        self.make_02(root)
        self.cli("upgrade", "docs/product/data-export.md", cwd=root)
        self.assertIn('okf_version: "0.2"', (root / "docs/index.md").read_text(encoding="utf-8"))
        self.assertTrue((root / "docs/log.md").read_text(encoding="utf-8").startswith("---"))


ACTIONS_MD = """---
type: action-list
title: Actions
description: Open and done actions from meetings.
x-okfdocs-class: tracker
generated:
  by: okf-docs/1.0.5
  at: 2026-11-01T09:00:00Z
---

# Actions

## Open

| Owner | Action | Due | From | Added |
|---|---|---|---|---|
| Sam | Set up the Initech pilot workspace | 2026-11-01 | [Initech call](assets/2026-10-30-initech-call.md) | 2026-10-30 |
| Kim | Send the contract | 2026-11-12 | - | 2026-10-30 |
| Lee | Book the offsite | 2026-12-01 | - | 2026-10-30 |
| Ann | Share the roadmap | - | - | 2026-10-30 |

## Done

| Owner | Action | Due | From | Added | Done |
|---|---|---|---|---|---|
| Sam | Old task | 2026-05-01 | - | 2026-04-20 | 2026-05-02 |
| Sam | Recent task | 2026-10-01 | - | 2026-09-20 | 2026-11-05 |
"""

QUESTIONS_MD = """---
type: question-list
title: Questions
description: Open questions about the company.
x-okfdocs-class: tracker
generated:
  by: okf-docs/1.0.5
  at: 2026-11-01T09:00:00Z
---

# Questions

## Open

| Area | Question | Why it matters | Asked |
|---|---|---|---|
| Selling | Who approves discounts above 20%? | Sales process file and decision rights | 2026-11-10 |
| Support | What is the response target? | Support file | 2026-11-10 |

## Answered

| Area | Question | Answer in | Answered |
|---|---|---|---|
| People | Who owns billing? | [team](people/team.md) | 2026-06-01 |
"""


class TestBrainConfig(Base):
    """Config `brain.actions` and `brain.names`, and the BRAIN context line."""

    def config(self, root, brain_block):
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + brain_block, encoding="utf-8")

    def test_defaults(self):
        root = self.fixture("brain-repo")
        project = self.project(root)
        self.assertEqual((project.brain_actions, project.brain_names), ("report", "team"))
        self.assertEqual(project.config_issues, [])
        self.assertIn("BRAIN actions=report names=team", self.cli("context", cwd=root).stdout)

    def test_values_are_read(self):
        root = self.fixture("brain-repo")
        self.config(root, "brain:\n  actions: track\n  names: Roles\n")
        project = self.project(root)
        self.assertEqual((project.brain_actions, project.brain_names), ("track", "roles"))
        out = self.cli("context", cwd=root).stdout
        self.assertIn("BRAIN actions=track names=roles", out)
        self.assertNotIn("CONFIG_VALUE", out)

    def test_bad_values_are_reported_and_use_the_default(self):
        root = self.fixture("brain-repo")
        self.config(root, "brain:\n  actions: maybe\n  names: all\n")
        project = self.project(root)
        self.assertEqual((project.brain_actions, project.brain_names), ("report", "all"))
        self.assertEqual(len(project.config_issues), 1)
        self.assertIn("`brain.actions` is 'maybe'; use one of: report, track, off", project.config_issues[0])
        out = self.cli("context", cwd=root).stdout
        self.assertIn("BRAIN actions=report names=all", out)
        self.assertIn("CONFIG_VALUE: .okf/config.yaml: `brain.actions` is 'maybe'", out)
        res = self.cli("check", "--json", cwd=root)
        found = [f for f in json.loads(res.stdout)["findings"] if f["code"] == "config-value"]
        self.assertEqual((found[0]["path"], found[0]["level"], found[0]["severity"]),
                         (".okf/config.yaml", "house", "warn"))

    def test_brain_that_is_not_a_mapping(self):
        root = self.fixture("brain-repo")
        self.config(root, "brain: track\n")
        project = self.project(root)
        self.assertEqual((project.brain_actions, project.brain_names), ("report", "team"))
        self.assertIn("must be a mapping", project.config_issues[0])

    def test_no_brain_line_without_the_module(self):
        out = self.cli("context", cwd=self.fixture("repo")).stdout
        self.assertNotIn("BRAIN actions=", out)


class TestTrackers(Base):
    """Tracker files: actions.md and questions.md at a brain root."""

    def brain(self, actions=ACTIONS_MD, questions=QUESTIONS_MD):
        root = self.tmp / "brain-repo"
        if not root.exists():
            self.fixture("brain-repo")
        for name, text in (("actions.md", actions), ("questions.md", questions)):
            if text is None:
                (root / "brain" / name).unlink(missing_ok=True)
            else:
                (root / "brain" / name).write_text(text, encoding="utf-8")
        return root

    def found(self, root, path, code=None):
        return [f for f in self.findings(root) if f.path == path and (code is None or f.code == code)]

    def test_tracker_is_a_class(self):
        self.assertIn("tracker", okf.ENUMS["class"])
        root = self.brain()
        self.assertEqual(self.found(root, "brain/actions.md", "enum-value"), [])
        doc = okf.Doc.load(self.project(root).bundles[0], root / "brain/actions.md")
        self.assertEqual((doc.klass, okf.tracker_kind(doc)), ("tracker", "actions"))

    def test_parse_actions(self):
        root = self.brain()
        doc = okf.Doc.load(self.project(root).bundles[0], root / "brain/actions.md")
        info = okf.parse_tracker(doc)
        self.assertTrue(info["open_ok"] and info["closed_ok"])
        self.assertEqual([r["Owner"] for _, r in info["open"]], ["Sam", "Kim", "Lee", "Ann"])
        self.assertEqual(info["open"][0][1]["From"], "[Initech call](assets/2026-10-30-initech-call.md)")
        self.assertEqual(info["open"][3][1]["Due"], "-")
        self.assertEqual([r["Done"] for _, r in info["closed"]], ["2026-05-02", "2026-11-05"])
        line = doc.text.split("\n").index(next(l for l in doc.text.split("\n") if "| Sam | Set up" in l)) + 1
        self.assertEqual(info["open"][0][0], line)

    def test_parse_questions_and_empty_tables(self):
        root = self.brain()
        doc = okf.Doc.load(self.project(root).bundles[0], root / "brain/questions.md")
        info = okf.parse_tracker(doc)
        self.assertEqual(len(info["open"]), 2)
        self.assertEqual(info["closed"][0][1]["Answer in"], "[team](people/team.md)")
        empty = ACTIONS_MD.split("## Open")[0] + (
            "## Open\n\n| Owner | Action | Due | From | Added |\n|---|---|---|---|---|\n\n"
            "## Done\n\n| Owner | Action | Due | From | Added | Done |\n|---|---|---|---|---|---|\n")
        root = self.brain(actions=empty)
        info = okf.parse_tracker(okf.Doc.load(self.project(root).bundles[0], root / "brain/actions.md"))
        self.assertEqual((info["open"], info["closed"], info["open_ok"]), ([], [], True))

    def test_overdue_actions(self):
        root = self.brain()
        found = self.found(root, "brain/actions.md", "action-overdue")  # the clock is 2026-11-12
        self.assertEqual(len(found), 1)  # due today is not overdue; `-` has no date
        self.assertEqual((found[0].level, found[0].severity), ("content", "info"))
        self.assertEqual(found[0].message, "Sam: Set up the Initech pilot workspace was due 2026-11-01")
        self.assertTrue(found[0].line)

    def test_format_warning(self):
        bad_header = ACTIONS_MD.replace("| Owner | Action | Due | From | Added |", "| Who | Action | Due | From | Added |")
        found = self.found(self.brain(actions=bad_header), "brain/actions.md", "tracker-format")
        self.assertEqual((found[0].level, found[0].severity), ("house", "warn"))
        self.assertIn("Open table header", found[0].message)
        no_open = ACTIONS_MD.replace("## Open", "## Todo")
        found = self.found(self.brain(actions=no_open), "brain/actions.md", "tracker-format")
        self.assertIn("no `## Open` table", found[0].message)
        self.assertEqual(self.found(self.brain(), "brain/actions.md", "tracker-format"), [])
        bad_q = QUESTIONS_MD.replace("| Area | Question | Why it matters | Asked |", "| Area | Question | Asked |")
        self.assertEqual(len(self.found(self.brain(questions=bad_q), "brain/questions.md", "tracker-format")), 1)

    def test_prune_info(self):
        root = self.brain()
        a = self.found(root, "brain/actions.md", "tracker-prune")
        self.assertEqual((a[0].level, a[0].severity), ("house", "info"))
        self.assertEqual(a[0].message, "1 done row older than 90 days; propose removing it")
        q = self.found(root, "brain/questions.md", "tracker-prune")
        self.assertEqual(q[0].message, "1 answered row older than 90 days; propose removing it")
        fresh = ACTIONS_MD.replace("2026-05-02", "2026-11-01")
        self.assertEqual(self.found(self.brain(actions=fresh), "brain/actions.md", "tracker-prune"), [])

    def test_trackers_skip_the_review_queue_and_source_checks(self):
        text = ACTIONS_MD.replace("---\n\n# Actions", "stale_after: 2026-01-01T00:00:00Z\n"
                                  "sources:\n  - resource: assets/missing.md\n---\n\n# Actions")
        root = self.brain(actions=text, questions=QUESTIONS_MD.replace("2026-11-01T09", "2020-01-01T09"))
        codes = {f.code for f in self.findings(root) if f.path in ("brain/actions.md", "brain/questions.md")}
        self.assertFalse(codes & {"unverified", "verification-outdated", "stale", "delete-candidate",
                                  "source-missing", "duplicate-title"}, codes)
        project = self.project(root)
        queue = okf.stale_queue(project, self.ctx(project))
        self.assertFalse([q for q in queue if q["path"] in ("brain/actions.md", "brain/questions.md")])
        ctx = self.ctx(project, at=dt.datetime(2030, 1, 1, tzinfo=UTC))
        self.assertEqual(ctx.decay_weight(okf.Doc.load(project.bundles[0], root / "brain/questions.md")), (1.0, None))
        self.assertTrue(queue)  # other files still queue

    def test_generated_is_still_checked_on_trackers(self):
        text = ACTIONS_MD.replace("  by: okf-docs/1.0.5\n", "")
        codes = {f.code for f in self.findings(self.brain(actions=text)) if f.path == "brain/actions.md"}
        self.assertIn("generated-by-missing", codes)

    def test_duplicate_title_between_tracker_and_note_is_ignored(self):
        root = self.brain()
        (root / "brain/company/actions.md").write_text(ACTIONS_MD.replace("type: action-list\n", "type: concept\n")
                                                       .replace("x-okfdocs-class: tracker\n", ""), encoding="utf-8")
        self.assertEqual([f for f in self.findings(root) if f.code == "duplicate-title"], [])

    def test_context_trackers_line_and_directives(self):
        far = ACTIONS_MD.replace("2026-11-01 |", "2020-01-01 |").replace("2026-11-12 |", "2020-02-01 |") \
                        .replace("2026-12-01 |", "2099-12-01 |")
        root = self.brain(actions=far)
        out = self.cli("context", cwd=root).stdout
        self.assertIn("TRACKERS brain/ actions_open=4 overdue=2 questions_open=2", out)
        self.assertIn("- ACTIONS: 2 overdue actions in brain/actions.md; mention them in the status.", out)
        self.assertIn("- QUESTIONS: 2 open questions in brain/questions.md; offer to go through them when the "
                      "user works on the brain.", out)
        rep = json.loads(self.cli("context", "--json", cwd=root).stdout)
        self.assertEqual(rep["bundles"][0]["trackers"], {"actions_open": 4, "overdue": 2, "questions_open": 2})

    def test_context_without_overdue_or_questions(self):
        calm = ACTIONS_MD.replace("2026-11-01 |", "2099-01-01 |").replace("2026-11-12 |", "2099-01-02 |")
        empty_q = QUESTIONS_MD.split("| Selling")[0] + "\n## Answered\n\n| Area | Question | Answer in | Answered |\n|---|---|---|---|\n"
        root = self.brain(actions=calm, questions=empty_q)
        out = self.cli("context", cwd=root).stdout
        self.assertIn("TRACKERS brain/ actions_open=4 overdue=0 questions_open=0", out)
        self.assertNotIn("- ACTIONS:", out)
        self.assertNotIn("- QUESTIONS:", out)

    def test_context_omits_missing_tracker_fields(self):
        out = self.cli("context", cwd=self.brain(actions=None)).stdout
        self.assertIn("TRACKERS brain/ questions_open=2", out)
        self.assertNotIn("actions_open", out)
        out = self.cli("context", cwd=self.brain(questions=None)).stdout
        self.assertRegex(out, r"TRACKERS brain/ actions_open=4 overdue=\d+\n")
        self.assertNotIn("TRACKERS", self.cli("context", cwd=self.brain(actions=None, questions=None)).stdout)

    def test_tracker_is_listed_in_the_index(self):
        root = self.brain()
        project = self.project(root)
        text, _ = okf.build_index(project.bundles[0], root / "brain", self.ctx(project))
        self.assertIn("(actions.md)", text)
        self.assertIn("(questions.md)", text)


class TestCapture(Base):
    """The Stop hook, the Review log kind, promotion-candidate and BRAIN_REVIEW."""

    def repo(self, capture=True):
        root = self.fixture("repo")
        if capture:
            cfg = root / ".okf/config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace("edits: true", "edits: true\n  capture: true"),
                           encoding="utf-8")
        return root

    def transcript(self, entries, name="t.jsonl"):
        path = self.tmp / name
        path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in entries) + "\n",
                        encoding="utf-8")
        return path

    @staticmethod
    def user(text):
        return {"type": "user", "message": {"role": "user", "content": text}}

    @staticmethod
    def result():
        return {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}

    @staticmethod
    def edit(path, tool="Edit"):
        return {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "x", "name": tool, "input": {"file_path": str(path)}}]}}

    def stop(self, root, transcript, session="s1", active=False, state=True, raw=None):
        payload = raw if raw is not None else json.dumps({
            "session_id": session, "transcript_path": str(transcript), "cwd": str(root),
            "hook_event_name": "Stop", "stop_hook_active": active})
        args = ["stop"] + (["--state", str(self.tmp / "state")] if state else [])
        r = self.cli(*args, cwd=root, stdin=payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_fires_once_after_an_edit(self):
        root = self.repo()
        t = self.transcript([self.user("fix it"), self.edit(root / "src/export/job.ts")])
        out = self.stop(root, t)
        self.assertEqual(out, {"decision": "block", "reason": okf.STOP_REMINDER})
        self.assertTrue(out["reason"].startswith("okf-docs: before finishing, check this session"))
        self.assertIsNone(self.stop(root, t))
        self.assertIsNotNone(self.stop(root, t, session="s2"))

    def test_edit_tools_and_relative_paths(self):
        root = self.repo()
        for tool in ("Write", "MultiEdit"):
            t = self.transcript([self.edit("src/a.ts", tool)])
            self.assertIsNotNone(self.stop(root, t, session=tool))

    def test_edits_inside_bundles_do_not_count(self):
        root = self.repo()
        t = self.transcript([self.user("x"), self.edit(root / "docs/index.md"), self.edit(root / "help/index.md")])
        self.assertIsNone(self.stop(root, t))

    def test_four_user_messages_count_but_tool_results_do_not(self):
        root = self.repo()
        t = self.transcript([self.user("a"), self.result(), self.user("b"), self.result(), self.result(),
                             self.result(), self.user("c")])
        self.assertIsNone(self.stop(root, t))
        t = self.transcript([self.user("a"), "not json", self.user("b"), self.result(), self.user("c"),
                             {"type": "user", "message": {"content": [{"type": "text", "text": "d"}]}}], "t2.jsonl")
        self.assertIsNotNone(self.stop(root, t))

    def test_no_op_cases(self):
        root = self.repo()
        t = self.transcript([self.edit(root / "src/a.ts")])
        self.assertIsNone(self.stop(root, t, active=True))
        self.assertIsNone(self.stop(root, self.tmp / "missing.jsonl"))
        self.assertIsNone(self.stop(root, self.tmp))  # a folder, unreadable as a file
        for raw in ("", "not json", "[]", "{}"):
            self.assertIsNone(self.stop(root, t, raw=raw))
        self.assertIsNotNone(self.stop(root, t))

    def test_no_state_folder_falls_back_to_the_temp_folder(self):
        root = self.repo()
        t = self.transcript([self.edit(root / "src/a.ts")])
        self.assertIsNotNone(self.stop(root, t, state=False))
        self.assertIsNone(self.stop(root, t, state=False))
        self.assertTrue((self.tmp / "okf-docs" / "stop-reminded.json").exists())

    def test_harness_messages_are_not_user_messages(self):
        root = self.repo()
        harness = [self.user("<task-notification>\n<task-id>x</task-id>"), self.user("<local-command-stdout>ok"),
                   self.user("  <command-name>/clear</command-name>"),
                   dict(self.user("summary of the earlier conversation"), isCompactSummary=True)]
        t = self.transcript([self.user("one real message")] + harness)
        self.assertIsNone(self.stop(root, t))
        t = self.transcript([self.user("a"), self.user("b"), self.user("c"), self.user("d")], name="t2.jsonl")
        self.assertIsNotNone(self.stop(root, t, session="s2"))

    def test_edits_outside_the_project_do_not_count(self):
        root = self.repo()
        t = self.transcript([self.user("x"), self.edit(self.tmp / "elsewhere/notes.md"),
                             self.edit(self.home / ".claude/memory.md")])
        self.assertIsNone(self.stop(root, t))

    def test_off_by_default_and_without_config(self):
        root = self.repo(capture=False)
        t = self.transcript([self.edit(root / "src/a.ts")])
        self.assertIsNone(self.stop(root, t))
        legacy = self.fixture("legacy")
        self.assertIsNone(self.stop(legacy, t))

    def test_unwritable_state_is_a_no_op(self):
        root = self.repo()
        t = self.transcript([self.edit(root / "src/a.ts")])
        blocker = self.tmp / "state"
        blocker.write_text("a file, not a folder", encoding="utf-8")
        self.assertIsNone(self.stop(root, t))

    def test_capture_shows_in_context(self):
        root = self.repo(capture=False)
        self.assertIn("HOOKS session=on edits=on capture=off", self.cli("context", cwd=root).stdout)
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("edits: true", "edits: true\n  capture: true"),
                       encoding="utf-8")
        self.assertIn("HOOKS session=on edits=on capture=on", self.cli("context", cwd=root).stdout)

    def test_hooks_json_has_the_stop_entry(self):
        data = json.loads((SCRIPT.parents[3] / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        hook = data["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(hook["type"], "command")
        self.assertEqual(hook["timeout"], 10)
        self.assertIn('stop --state \"${CLAUDE_PLUGIN_DATA}\"', hook["command"])
        self.assertIn("[ -f \"$S\" ] || exit 0", hook["command"])
        self.assertTrue(hook["command"].endswith("exit 0"))
        self.assertEqual(set(data["hooks"]), {"SessionStart", "PostToolUse", "Stop"})

    def test_review_log_kind(self):
        folder = self.tmp / "bundle"
        folder.mkdir()
        r = self.cli("log", str(folder), "Review", "Proposed 3 changes; applied 2.", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("* **Review**: Proposed 3 changes; applied 2.", (folder / "log.md").read_text(encoding="utf-8"))
        self.assertIn("Review", self.cli("log", "--help").stdout)

    OBS = """---
type: observation
x-okfdocs-class: observation
title: %s
description: Customers ask for it.
status: %s
generated:
  by: human:tester
  at: 2026-11-01T09:00:00Z
stale_after: 2027-02-01T00:00:00Z
sources:
%s---

# %s

Customers ask for it.
"""

    def observation(self, root, name, sources, status="stable"):
        lines = "".join("  - resource: %s\n" % s for s in sources)
        path = root / "brain/observations" / name
        path.write_text(self.OBS % (name, status, lines, name), encoding="utf-8")
        return path

    def candidates(self, root):
        return [f.path for f in self.findings(root) if f.code == "promotion-candidate"]

    def test_no_promotion_for_promoted_or_stale_observations(self):
        root = self.fixture("brain-repo")
        two = ["../assets/2026-05-28-customer-call-globex.md", "files/b.txt"]
        promoted = self.observation(root, "2026-11-02-promoted.md", two)
        promoted.write_text(promoted.read_text(encoding="utf-8").replace(
            "status: stable", "status: stable\nsuperseded_by: ../market/audiences.md"), encoding="utf-8")
        stale = self.observation(root, "2026-11-02-stale.md", two)
        stale.write_text(stale.read_text(encoding="utf-8").replace(
            "stale_after: 2027-02-01T00:00:00Z", "stale_after: 2020-01-01T00:00:00Z"), encoding="utf-8")
        self.assertEqual(self.candidates(root), [])

    def test_promotion_candidate(self):
        root = self.fixture("brain-repo")
        self.observation(root, "2026-11-02-two.md", ["../assets/2026-05-28-customer-call-globex.md", "files/b.txt"])
        self.observation(root, "2026-11-02-one.md", ["../assets/2026-05-28-customer-call-globex.md"])
        self.observation(root, "2026-11-02-same.md", ["files/a.txt", "files/a.txt"])
        self.observation(root, "2026-11-02-old.md", ["files/a.txt", "files/b.txt"], status="deprecated")
        found = [f for f in self.findings(root) if f.code == "promotion-candidate"]
        self.assertEqual([f.path for f in found], ["brain/observations/2026-11-02-two.md"])
        self.assertEqual((found[0].level, found[0].severity), ("content", "info"))
        self.assertEqual(found[0].message, "supported by 2 sources; propose promoting it (lifecycle.md, Promotion)")
        self.assertNotIn("promotion-candidate", okf.AGGREGATED)

    def asset(self, root, day, name=None, generated=True):
        gen = "generated:\n  by: human:tester\n  at: %sT09:00:00Z\n" % day if generated else ""
        path = root / "brain/assets" / ("%s-%s.md" % (day, name or "call"))
        path.write_text("---\ntype: meeting\nx-okfdocs-class: asset\ntitle: Call %s\ndescription: A call.\n%s---\n\n# Call\n"
                        % (path.stem, gen), encoding="utf-8")

    def review_line(self, root):
        out = self.cli("context", cwd=root).stdout
        return [l for l in out.splitlines() if l.startswith("- BRAIN_REVIEW:")]

    def test_brain_review_needs_three_assets(self):
        root = self.fixture("brain-repo")  # one asset (2026-05-28), no Review entry yet
        self.asset(root, "2026-11-03")
        self.assertEqual(self.review_line(root), [])
        self.asset(root, "2026-11-04", generated=False)  # the dated filename counts
        self.assertEqual(self.review_line(root), [
            "- BRAIN_REVIEW: 3 assets added since the last brain review (never); offer /okf-docs check brain."])

    def test_brain_review_counts_only_assets_after_the_last_review(self):
        root = self.fixture("brain-repo")
        for day in ("2026-11-03", "2026-11-04", "2026-11-05"):
            self.asset(root, day)
        okf.add_log_entry(root / "brain", "Review", "Promoted one.", today="2026-11-04")
        self.assertEqual(self.review_line(root), [])  # only 2026-11-05 is after it
        self.asset(root, "2026-11-06")
        self.asset(root, "2026-11-07")
        self.assertEqual(self.review_line(root), [
            "- BRAIN_REVIEW: 3 assets added since the last brain review (2026-11-04); offer /okf-docs check brain."])
        self.assertEqual(okf.last_log_date_of(root / "brain/log.md", "Review"), "2026-11-04")


class TestReviewFixes(Base):
    """Regressions from the code review of the helper script."""

    DATA = "docs/product/data-export.md"

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def edit(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def read(self, root, rel):
        return (root / rel).read_text(encoding="utf-8")

    def unversioned(self, root):
        """docs/ with no okf_version, a root index without frontmatter and a bare root-relative path."""
        self.write(root / "docs/index.md", "# Sections\n\n* [Product](product/) - What it does.\n"
                   "* [System](system/) - How it's built.\n* [Decisions](decisions/) - Why.\n")
        self.edit(root / self.DATA, "resource: ../decisions/002-json-export.md",
                  "resource: decisions/002-json-export.md")

    # 1 ----------------------------------------------------------------------
    def test_fix_and_index_do_not_declare_a_version_before_upgrade(self):
        root = self.fixture("repo")
        self.unversioned(root)
        self.cli("check", "--fix", cwd=root)
        self.assertNotIn("okf_version", self.read(root, "docs/index.md"))
        self.cli("index", "--write", cwd=root)
        self.assertNotIn("okf_version", self.read(root, "docs/index.md"))
        self.assertFalse(self.read(root, "docs/index.md").startswith("---"))
        (root / "docs/index.md").unlink()  # fix writes a missing root index without a version, too
        self.cli("check", "--fix", cwd=root)
        self.assertTrue((root / "docs/index.md").exists())
        self.assertNotIn("okf_version", self.read(root, "docs/index.md"))
        out = self.cli("upgrade", cwd=root)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("../decisions/002-json-export.md", self.read(root, self.DATA))
        self.assertIn('okf_version: "0.3"', self.read(root, "docs/index.md"))

    # 2 ----------------------------------------------------------------------
    def make_fallback_shapes(self, root):
        self.edit(root / "docs/index.md", 'okf_version: "0.3"', 'okf_version: "0.2"')
        self.write(root / "docs/LICENSE", "MIT\n")
        self.write(root / "docs/product/extra.md",
                   "---\ntype: concept\ntitle: Extra\ndescription: Extra page.\n"
                   "superseded_by:\n  - decisions/002-json-export.md\n"
                   "sources:\n  - resource: LICENSE\n---\n\n# Extra\n")

    def test_upgrade_rewrites_list_superseded_by_and_extensionless_sources(self):
        root = self.fixture("repo")
        self.make_fallback_shapes(root)
        extra = root / "docs/product/extra.md"
        labels = {f.message.split(" ")[0] for f in self.findings(root)
                  if f.code == "path-root-fallback" and f.path == "docs/product/extra.md"}
        self.assertEqual(labels, {"superseded_by", "sources[0].resource"})
        r = self.cli("upgrade", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = extra.read_text(encoding="utf-8")
        self.assertIn("../decisions/002-json-export.md", text)
        self.assertIn("resource: ../LICENSE", text)
        self.assertEqual([f for f in self.findings(root) if f.code == "path-root-fallback"], [])
        self.assertIn('okf_version: "0.3"', self.read(root, "docs/index.md"))

    def test_upgrade_keeps_the_version_while_a_fallback_path_is_left(self):
        root = self.fixture("repo")
        self.make_fallback_shapes(root)
        real, quiet = okf._fix_fallback, io.StringIO()
        okf._fix_fallback = lambda doc, value, ctx: None if value == "LICENSE" else real(doc, value, ctx)
        try:
            with contextlib.redirect_stdout(quiet):
                okf.main(["upgrade", "--project", str(root)])
        finally:
            okf._fix_fallback = real
        self.assertIn('okf_version: "0.2"', self.read(root, "docs/index.md"))
        self.assertIn("LICENSE", quiet.getvalue())
        self.assertIn("stays", quiet.getvalue())
        self.assertIn("../decisions/002-json-export.md", self.read(root, "docs/product/extra.md"))

    # 3 ----------------------------------------------------------------------
    def notes_folder(self, root):
        self.write(root / "docs/notes/README.md", "# Notes\n\nHow to use this folder.\n")
        self.write(root / "docs/notes/index.md", "---\ntitle: Notes\n---\n\n# Notes\n")
        idx = root / "docs/index.md"
        idx.write_text(idx.read_text(encoding="utf-8") + "* [Notes](notes/) - Working notes.\n", encoding="utf-8")

    def test_a_folder_with_only_non_concepts_is_not_a_delete_candidate(self):
        root = self.fixture("repo")
        self.notes_folder(root)
        found = self.findings(root)
        self.assertEqual([f for f in found if f.code == "delete-candidate"], [])
        self.assertEqual([f.message for f in found if f.code == "index-stale" and f.path == "docs/index.md"], [])
        self.assertEqual([f.code for f in found if f.path == "docs/notes/index.md"], ["index-frontmatter"])
        project = self.project(root)
        self.assertEqual(project.bundles[0].emptied_dirs(), [])

    def test_a_folder_emptied_of_every_file_is_still_a_delete_candidate(self):
        root = self.fixture("repo")
        (root / "docs/decisions/001-csv-first.md").unlink()
        (root / "docs/decisions/002-json-export.md").unlink()
        self.assertEqual([f.path for f in self.findings(root) if f.code == "delete-candidate"], ["docs/decisions/"])

    def test_upgrade_strips_the_frontmatter_of_a_non_concept_folder_index(self):
        root = self.fixture("repo")
        self.notes_folder(root)
        r = self.cli("upgrade", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("docs/notes/index.md", r.stdout)
        self.assertEqual(self.read(root, "docs/notes/index.md").strip(), "# Notes")
        self.assertTrue((root / "docs/notes/README.md").exists())

    # 4 ----------------------------------------------------------------------
    def test_tracker_header_case_does_not_hide_rows(self):
        lower = ACTIONS_MD.replace("| Owner | Action | Due | From | Added |", "| owner | action | due | from | added |") \
                          .replace("| Owner | Action | Due | From | Added | Done |", "| owner | action | due | from | added | done |")
        root = TestTrackers.brain(self, actions=lower)
        found = [f for f in self.findings(root) if f.path == "brain/actions.md"]
        self.assertEqual([f.code for f in found if f.code == "tracker-format"], [])
        self.assertEqual(len([f for f in found if f.code == "action-overdue"]), 1)
        self.assertEqual(len([f for f in found if f.code == "tracker-prune"]), 1)
        project = self.project(root)
        self.assertEqual(okf.tracker_counts(project.bundles[0], self.ctx(project)), {"actions_open": 4, "overdue": 1,
                                                                                     "questions_open": 2})

    # 5 ----------------------------------------------------------------------
    def test_tracker_ignores_rows_and_headings_inside_fences(self):
        fenced = ACTIONS_MD.replace("\n## Done\n", "\n```\n## Done\n| Zed | Fake | 2020-01-01 | - | 2020-01-01 |\n```\n\n## Done\n")
        root = TestTrackers.brain(self, actions=fenced)
        doc = okf.Doc.load(self.project(root).bundles[0], root / "brain/actions.md")
        info = okf.parse_tracker(doc)
        self.assertEqual([r["Owner"] for _, r in info["open"]], ["Sam", "Kim", "Lee", "Ann"])
        self.assertEqual([r["Done"] for _, r in info["closed"]], ["2026-05-02", "2026-11-05"])
        self.assertTrue(info["closed_ok"])
        tilde = ACTIONS_MD.replace("| Ann |", "~~~\n| Zed | Fake | 2020-01-01 | - | 2020-01-01 |\n~~~\n| Ann |")
        doc = okf.Doc.load(self.project(root).bundles[0], TestTrackers.brain(self, actions=tilde) / "brain/actions.md")
        self.assertEqual([r["Owner"] for _, r in okf.parse_tracker(doc)["open"]], ["Sam", "Kim", "Lee", "Ann"])

    # 6 ----------------------------------------------------------------------
    def test_trust_drop_names_the_date_of_the_events_that_stopped_counting(self):
        root = self.fixture("repo")
        self.edit(root / self.DATA, "at: 2026-11-01T10:00:00+01:00", "at: 2026-11-04T12:00:00Z")
        self.edit(root / self.DATA, "    at: 2026-11-02T09:00:00+01:00",
                  "    at: 2026-11-02T12:00:00Z\n  - by: okf-docs/1.0.5\n    at: 2026-11-06T12:00:00Z")
        project = self.project(root)
        doc = okf.Doc.load(project.bundles[0], root / self.DATA)
        old, new, why = okf.trust_drop(doc)
        self.assertEqual((old, new), ("human-reviewed", "machine-confirmed"))
        self.assertEqual(why, "verified %s is older than generated.at %s" % (
            okf.fmt_date(okf.parse_ts("2026-11-02T12:00:00Z")[0]), okf.fmt_date(okf.parse_ts("2026-11-04T12:00:00Z")[0])))

    # 7 ----------------------------------------------------------------------
    def test_compared_timestamp_keys(self):
        self.assertTrue(okf.is_compared_ts("generated.at"))
        self.assertTrue(okf.is_compared_ts("verified[0].at"))
        self.assertFalse(okf.is_compared_ts("stale_after"))
        self.assertFalse(okf.is_compared_ts("sources[0].last_modified"))


class TestHumanActor(Base):
    """The verifier id comes only from OKF_ACTOR or `git config okf.actor`; git user.name is only a suggestion."""

    def setUp(self):
        super().setUp()
        os.environ.pop("OKF_ACTOR", None)
        self.root = self.fixture("repo")

    UNSET = ("human: not set (ask the person for their id; they can save it with "
             "git config --global okf.actor <id>)")

    def test_unset(self):
        self.assertEqual(okf.human_actor(self.project(self.root)), (None, "not set"))
        out = self.cli("now", cwd=self.root).stdout
        self.assertIn(self.UNSET, out)
        self.assertIn("agent: okf-docs/1.0.5", out)
        ctx = self.cli("context", cwd=self.root).stdout
        self.assertIn("ACTOR human not set (ask the person for their id; they can save it with "
                      "git config --global okf.actor <id>) · agent okf-docs/1.0.5", ctx)
        self.assertIsNone(json.loads(self.cli("context", "--json", cwd=self.root).stdout)["actor"]["human"])

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_git_user_name_is_only_a_suggestion(self):
        self.git(self.root, "init", "-q")
        self.git(self.root, "config", "user.name", "Alex Smith")
        os.environ["USER"] = os.environ["USERNAME"] = "alexs"
        self.assertEqual(okf.human_actor(self.project(self.root)), (None, "not set"))
        hint = ("not set; suggestion human:alex-smith (from git user.name): confirm it with the person, "
                "then save it with git config --global okf.actor alex-smith")
        self.assertIn("human: " + hint, self.cli("now", cwd=self.root).stdout)
        self.assertIn("ACTOR human " + hint, self.cli("context", cwd=self.root).stdout)
        rep = json.loads(self.cli("context", "--json", cwd=self.root).stdout)["actor"]
        self.assertEqual((rep["human"], rep["suggested"]), (None, "human:alex-smith"))
        self.git(self.root, "config", "okf.actor", "alex")
        rep = json.loads(self.cli("context", "--json", cwd=self.root).stdout)["actor"]
        self.assertEqual((rep["human"], rep["suggested"]), ("human:alex", None))

    def test_env(self):
        os.environ["OKF_ACTOR"] = "alex"
        self.assertEqual(okf.human_actor(self.project(self.root)), ("human:alex", "OKF_ACTOR"))
        os.environ["OKF_ACTOR"] = "human:alex-smith"
        self.assertEqual(okf.human_actor(self.project(self.root))[0], "human:alex-smith")
        self.assertIn("human: human:alex-smith   (from OKF_ACTOR)", self.cli("now", cwd=self.root).stdout)
        self.assertIn("ACTOR human:alex-smith (from OKF_ACTOR)", self.cli("context", cwd=self.root).stdout)

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_git_config(self):
        self.git(self.root, "init", "-q")
        self.git(self.root, "config", "okf.actor", "Pat Lee")
        self.assertEqual(okf.human_actor(self.project(self.root)), ("human:pat-lee", "git okf.actor"))
        self.assertIn("human: human:pat-lee   (from git okf.actor)", self.cli("now", cwd=self.root).stdout)
        os.environ["OKF_ACTOR"] = "alex"  # the environment wins
        self.assertEqual(okf.human_actor(self.project(self.root)), ("human:alex", "OKF_ACTOR"))


if __name__ == "__main__":
    unittest.main()


class TestFlagsAndFences(Base):
    """On/off config values and CommonMark fences."""

    def test_hook_switches_read_yaml_on_off_values(self):
        for value, expected in (("off", False), ("no", False), ("'false'", False), ("0", False), ("false", False),
                                ("on", True), ("yes", True), ("true", True), ("1", True)):
            cfg, _ = okf.yaml_load("hooks:\n  capture: %s\n  edits: %s\n" % (value, value))
            self.assertEqual((okf.hook_on(cfg, "capture"), okf.hook_on(cfg, "edits")), (expected, expected), value)
        cfg, _ = okf.yaml_load("hooks:\n  enabled: 'off'\n  session: no\n")
        self.assertEqual((okf.hook_on(cfg, "edits"), okf.hook_on(cfg, "session")), (False, False))
        self.assertTrue(okf.hook_on({}, "session"))

    def test_bad_hook_value_is_a_config_issue_and_uses_the_default(self):
        root = self.fixture("repo")
        cfg = root / ".okf/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("edits: true", "edits: maybe\n  capture: off"),
                       encoding="utf-8")
        project = self.project(root)
        self.assertFalse(okf.hook_on(project.config, "edits"))
        self.assertFalse(okf.hook_on(project.config, "capture"))
        self.assertEqual(len(project.config_issues), 1)
        self.assertIn("hooks.edits", project.config_issues[0])

    def test_check_reports_yaml11_differences_as_yaml_quote(self):
        root = self.fixture("repo")
        path = root / "docs/product/data-export.md"
        path.write_text(path.read_text(encoding="utf-8").replace("\ntitle:", "\ntags: [yes, exports]\ntitle:", 1),
                        encoding="utf-8")
        found = [f for f in self.findings(root) if f.path == "docs/product/data-export.md" and f.code == "yaml-quote"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].level, found[0].severity), ("okf", "warn"))
        self.assertIn("`yes`", found[0].message)

    def test_fence_step(self):
        lines = ["````md", "```python", "| x |", "```", "````", "| y |", "~~~", "```", "~~~", "| z |"]
        fence, inside = None, []
        for line in lines:
            fence, code = okf.fence_step(fence, line)
            inside.append(code)
        self.assertEqual(inside, [True, True, True, True, True, False, True, True, True, False])
        self.assertEqual(okf.fence_step(None, "``` inline ` code"), (None, False))

    def test_tracker_ignores_rows_in_a_long_fence(self):
        root = self.fixture("brain-repo")
        text = QUESTIONS_MD.replace("## Open", "````md\n```markdown\n## Open\n\n| Area | Question | Why it matters | Asked |\n"
                                    "|---|---|---|---|\n| Fake | Not a row? | - | 2026-11-01 |\n```\n````\n\n## Open", 1)
        (root / "brain/questions.md").write_text(text, encoding="utf-8")
        doc = okf.Doc.load(self.project(root).bundles[0], root / "brain/questions.md")
        info = okf.parse_tracker(doc)
        self.assertNotIn("Fake", [r["Area"] for _, r in info["open"]])

class TestYAMLCore(unittest.TestCase):
    """OKF 0.3 section 4: YAML 1.2 core schema, and a warning where YAML 1.1 tools read a value differently."""

    def test_core_schema_numbers(self):
        for text, want in (("0o17", 15), ("0x1f", 31), ("1e3", 1000.0), ("-2.5e-1", -0.25), (".inf", float("inf")),
                           ("-.Inf", float("-inf")), ("010", 10), ("yes", "yes"), ("off", "off"), ("1_000", "1_000"),
                           ("1:20", "1:20"), ("0.3", 0.3), ("2026-11-20", "2026-11-20")):
            self.assertEqual(okf.yaml_load("k: %s\n" % text)[0]["k"], want, text)
        nan = okf.yaml_load("k: .nan\n")[0]["k"]
        self.assertNotEqual(nan, nan)

    def test_yaml11_differences_warn(self):
        for text in ("yes", "No", "on", "OFF", "1:20", "010", "1_000", "0b101", "0o17", "1e3"):
            _, warnings = okf.yaml_load("k: %s\n" % text)
            self.assertEqual(len(warnings), 1, text)
            self.assertIn("YAML 1.1", warnings[0])
        for text in ("true", "5", "0", "2.5", "0x1f", ".inf", ".nan", "null", "abc", "'yes'", '"off"'):
            self.assertEqual(okf.yaml_load("k: %s\n" % text)[1], [], text)
        _, warnings = okf.yaml_load("tags: [yes, 'no', 3]\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("`yes`", warnings[0])

    def test_dump_quotes_what_differs(self):
        for text in ("yes", "off", "1:20", "010", "1_000", "0o17", "1e3"):
            self.assertTrue(okf.yaml_dump({"k": text})[0].startswith('k: "'), text)


class TestTrustModel(Base):
    """1.0.4: OKF tiers only, sources say where content came from, history lines are checked against git."""

    ORG = "brain/company/organization.md"
    ASSET = "brain/assets/2026-05-28-customer-call-globex.md"

    def test_sources_rank_inside_a_tier(self):
        root = self.fixture("repo")
        project = self.project(root)
        docs = {d.prel: d for b in project.bundles for d in b.docs}
        self.assertTrue(docs["docs/product/data-export.md"].sourced())
        self.assertFalse(docs["docs/decisions/002-json-export.md"].sourced())
        self.edit(root / "docs/product/data-export.md", "resource: ../decisions/002-json-export.md",
                  "resource: ../decisions/002-json-export.md\n    author: \"human:pat\"")
        doc = self.doc(root, "docs/product/data-export.md")
        self.assertEqual(doc.stated_by(), ["human:pat"])
        hits = okf.rank(self.project(root), self.ctx(self.project(root)), "export")
        self.assertEqual(next(h for h in hits if h["path"] == "docs/product/data-export.md")["stated_by"], ["human:pat"])

    def test_via_value(self):
        root = self.fixture("brain-repo")
        self.edit(root / self.ORG, "  - by: human:alex\n", "  - by: human:alex\n    x-okfdocs-via: chat\n")
        self.assertNotIn("via-value", self.codes(root, self.ORG))
        self.edit(root / self.ORG, "x-okfdocs-via: chat", "x-okfdocs-via: slack")
        self.assertIn("via-value", self.codes(root, self.ORG))

    def test_history_command(self):
        root = self.fixture("brain-repo")
        org = root / self.ORG
        before = org.read_text(encoding="utf-8")
        fm_before = before.split("\n---\n", 1)[0]
        r = self.cli("history", self.ORG, self.ASSET, "--note", "audit trail need", "--project", str(root))
        self.assertEqual(r.returncode, 0, r.stderr)
        text = org.read_text(encoding="utf-8")
        self.assertEqual(text.split("\n---\n", 1)[0], fm_before)  # frontmatter untouched
        line = "- 2026-05-28 [%s](../assets/2026-05-28-customer-call-globex.md): audit trail need" \
            % self.doc(root, self.ASSET).title
        self.assertIn("\n## History\n\n" + line + "\n", text)
        again = self.cli("history", self.ORG, self.ASSET, "--project", str(root))
        self.assertIn("already listed", again.stdout)
        self.assertEqual(org.read_text(encoding="utf-8"), text)
        newer = root / "brain/assets/2026-11-20-globex-follow-up.md"
        newer.write_text((root / self.ASSET).read_text(encoding="utf-8")
                         .replace("title: Customer call with Globex", "title: Follow-up call with Globex")
                         .replace("2026-05-28T16:00:00+02:00", "2026-11-20T16:00:00+01:00"), encoding="utf-8")
        self.cli("history", self.ORG, "brain/assets/2026-11-20-globex-follow-up.md", "--project", str(root))
        lines = [l for l in org.read_text(encoding="utf-8").split("\n") if l.startswith("- 20")]
        self.assertEqual([l[2:12] for l in lines], ["2026-11-20", "2026-05-28"])
        filed_later = root / "brain/assets/2026-11-12-initech-call.md"  # filed on the 24th, held on the 12th
        filed_later.write_text(newer.read_text(encoding="utf-8")
                               .replace("2026-11-20T16:00:00+01:00", "2026-11-24T08:00:00+01:00"), encoding="utf-8")
        out = self.cli("history", self.ORG, "brain/assets/2026-11-12-initech-call.md", "--project", str(root)).stdout
        self.assertIn("- 2026-11-12 [", out)
        self.assertEqual(self.doc(root, self.ORG).trust(), "human-reviewed")

    def test_history_lines_keep_order_newest_first(self):
        body = "# X\n\n## History\n\n- 2026-11-01 [b](b.md)\n- 2026-09-01 [a](a.md)\n\n## Related\n\n- [y](y.md)\n"
        out = okf.add_history_line(body, "- 2026-10-01 [c](c.md)", "2026-10-01")
        self.assertIn("- 2026-11-01 [b](b.md)\n- 2026-10-01 [c](c.md)\n- 2026-09-01 [a](a.md)\n\n## Related", out)
        out = okf.add_history_line(body, "- 2026-01-01 [d](d.md)", "2026-01-01")
        self.assertIn("- 2026-09-01 [a](a.md)\n- 2026-01-01 [d](d.md)\n\n## Related", out)
        self.assertEqual(okf.meaning_text({}, body), okf.meaning_text({}, out))
        self.assertNotEqual(okf.meaning_text({}, body), okf.meaning_text({}, body.replace("# X", "# Y")))

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_generated_not_bumped(self):
        root = self.fixture("brain-repo")
        org = root / self.ORG
        self.git(root, "init", "-q")
        self.git(root, "add", "-A")
        self.git(root, "commit", "-qm", "init", date="2026-10-02T00:00:00Z")
        codes = lambda: self.codes(root, self.ORG)
        self.assertNotIn("generated-not-bumped", codes())
        self.cli("history", self.ORG, self.ASSET, "--project", str(root))  # a history line: fine
        self.edit(org, "operations teams at mid-size", "operations  teams at\nmid-size")  # whitespace: fine
        self.assertNotIn("generated-not-bumped", codes())
        self.edit(org, "mid-size companies", "large companies")  # a change of meaning
        self.assertIn("generated-not-bumped", codes())
        self.edit(org, "at: 2026-10-01T09:00:00+02:00", "at: 2026-10-01T09:30:00+02:00")  # bumped, still
        self.assertNotIn("generated-not-bumped", codes())                                   # before the review
        self.edit(org, "at: 2026-10-01T09:30:00+02:00", "at: 2026-10-01T09:00:00+02:00")
        self.edit(org, "    at: 2026-10-01T10:00:00+02:00\n",
                  "    at: 2026-10-01T10:00:00+02:00\n  - by: human:pat\n    at: 2026-11-20T10:00:00+01:00\n")
        self.assertNotIn("generated-not-bumped", codes())  # a new review covers the new text

TICKETED_ACTIONS_MD = ACTIONS_MD.replace(
    "| Owner | Action | Due | From | Added |\n|---|---|---|---|---|\n",
    "| Owner | Action | Ticket | Due | From | Added |\n|---|---|---|---|---|---|\n").replace(
    "| Sam | Set up the Initech pilot workspace |", "| Sam | Set up the Initech pilot workspace | [ENG-412](https://linear.app/acme/issue/ENG-412) |").replace(
    "| Kim | Send the contract |", "| Kim | Send the contract | - |").replace(
    "| Lee | Book the offsite |", "| Lee | Book the offsite | |").replace(
    "| Ann | Share the roadmap |", "| Ann | Share the roadmap | |").replace(
    "| Owner | Action | Due | From | Added | Done |\n|---|---|---|---|---|---|\n",
    "| Owner | Action | Ticket | Due | From | Added | Done |\n|---|---|---|---|---|---|---|\n").replace(
    "| Sam | Old task |", "| Sam | Old task | - |").replace("| Sam | Recent task |", "| Sam | Recent task | - |")


class TestTickets(Base):
    """brain.tickets: ticket sync settings, the Ticket column and its findings."""

    def brain(self, actions=TICKETED_ACTIONS_MD, questions=QUESTIONS_MD, tickets="  tickets:\n    system: Linear\n    target: ENG\n",
              actions_mode="track"):
        shutil.rmtree(self.tmp / "brain-repo", ignore_errors=True)  # each call starts from a clean fixture
        root = TestTrackers.brain(self, actions=actions, questions=questions)
        cfg = root / ".okf/config.yaml"
        base = cfg.read_text(encoding="utf-8").split("brain:\n  actions")[0]
        cfg.write_text(base + "brain:\n  actions: %s\n" % actions_mode + (tickets or ""), encoding="utf-8")
        return root

    found = TestTrackers.found

    def test_tickets_are_read(self):
        project = self.project(self.brain())
        self.assertEqual(project.brain_tickets, {"system": "linear", "target": "ENG"})
        self.assertEqual(project.config_issues, [])
        out = self.cli("context", cwd=self.brain()).stdout
        self.assertIn("BRAIN actions=track names=team tickets=linear:ENG", out)
        self.assertIn("- TICKETS: meeting actions sync to linear (target ENG).", out)

    def test_off_by_default_and_with_none(self):
        for block in (None, "  tickets:\n    system: none\n", "  tickets:\n    system: off\n", "  tickets:\n"):
            root = self.brain(tickets=block)
            project = self.project(root)
            self.assertIsNone(project.brain_tickets, block)
            self.assertEqual(project.config_issues, [], block)
            out = self.cli("context", cwd=root).stdout
            self.assertIn("tickets=none", out)
            self.assertNotIn("TICKETS", out)
            self.assertEqual(self.found(root, "brain/actions.md", "action-unsynced"), [])

    def test_no_target_asks(self):
        out = self.cli("context", cwd=self.brain(tickets="  tickets:\n    system: jira\n")).stdout
        self.assertIn("tickets=jira:-", out)
        self.assertIn("no target set: ask which team, project or repository the first time", out)

    def test_bad_values_turn_sync_off(self):
        for block, needle in (("  tickets: linear\n", "must be a mapping"),
                              ("  tickets:\n    system: [linear]\n", "`brain.tickets.system` is ['linear']"),
                              ("  tickets:\n    system: linear\n    target: [ENG]\n", "`brain.tickets.target`")):
            root = self.brain(tickets=block)
            project = self.project(root)
            self.assertIsNone(project.brain_tickets, block)
            self.assertEqual(len(project.config_issues), 1, block)
            self.assertIn(needle, project.config_issues[0])
            self.assertIn("CONFIG_VALUE", self.cli("context", cwd=root).stdout)

    def test_actions_off_reports_and_disables_sync(self):
        root = self.brain(actions_mode="off")
        project = self.project(root)
        self.assertIsNone(project.brain_tickets)
        self.assertIn("`brain.actions` is off", project.config_issues[0])

    def test_ticket_column_is_parsed(self):
        root = self.brain()
        info = okf.parse_tracker(okf.Doc.load(self.project(root).bundles[0], root / "brain/actions.md"))
        self.assertTrue(info["open_ok"] and info["closed_ok"] and info["ticket_column"])
        self.assertEqual(info["open"][0][1]["Ticket"], "[ENG-412](https://linear.app/acme/issue/ENG-412)")
        self.assertEqual(info["open"][0][1]["Due"], "2026-11-01")
        self.assertEqual([r["Done"] for _, r in info["closed"]], ["2026-05-02", "2026-11-05"])
        self.assertEqual(len(self.found(root, "brain/actions.md", "action-overdue")), 1)
        self.assertEqual(len(self.found(root, "brain/actions.md", "tracker-prune")), 1)
        self.assertEqual(self.found(root, "brain/actions.md", "tracker-format"), [])

    def test_ticket_column_is_fine_without_sync(self):
        root = self.brain(tickets=None)
        self.assertEqual(self.found(root, "brain/actions.md", "tracker-format"), [])
        self.assertEqual(self.found(root, "brain/actions.md", "action-unsynced"), [])

    def test_unsynced_actions(self):
        root = self.brain()
        found = self.found(root, "brain/actions.md", "action-unsynced")
        self.assertEqual([f.message for f in found], [  # a link or `-` counts as synced
            "Lee: Book the offsite has no ticket in linear yet; sync it, or put - when it needs none",
            "Ann: Share the roadmap has no ticket in linear yet; sync it, or put - when it needs none"])
        self.assertEqual((found[0].level, found[0].severity), ("content", "info"))
        self.assertTrue(found[0].line)
        out = self.cli("context", cwd=root).stdout
        self.assertRegex(out, r"TRACKERS brain/ actions_open=4 overdue=\d+ unsynced=2 questions_open=2\n")
        self.assertIn("- TICKETS_PENDING: 2 open actions in brain/actions.md have no ticket yet; offer to sync them.", out)

    def test_old_table_with_sync_on(self):
        root = self.brain(actions=ACTIONS_MD)
        found = self.found(root, "brain/actions.md", "tracker-format")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].level, found[0].severity), ("house", "info"))
        self.assertIn("add a Ticket column after Action", found[0].message)
        self.assertEqual(self.found(root, "brain/actions.md", "action-unsynced"), [])
        rep = json.loads(self.cli("context", "--json", cwd=root).stdout)
        self.assertEqual(rep["bundles"][0]["trackers"]["unsynced"], 4)
        self.assertEqual(rep["brain"]["tickets"], {"system": "linear", "target": "ENG"})

    def test_bad_header_names_the_ticket_header(self):
        bad = TICKETED_ACTIONS_MD.replace("| Owner | Action | Ticket | Due | From | Added |",
                                          "| Owner | Action | Issue | Due | From | Added |")
        found = self.found(self.brain(actions=bad), "brain/actions.md", "tracker-format")
        self.assertEqual(found[0].severity, "warn")
        self.assertIn("Owner | Action | Ticket | Due | From | Added", found[0].message)

    def test_questions_take_no_ticket_column(self):
        q = QUESTIONS_MD.replace("| Area | Question | Why it matters | Asked |", "| Area | Question | Ticket | Why it matters | Asked |")
        self.assertEqual(len(self.found(self.brain(questions=q), "brain/questions.md", "tracker-format")), 1)

    def test_template_config_reads_clean(self):
        root = self.fixture("repo")
        tmpl = (HERE.parent / "okf-docs/skills/okf-docs/templates/config.yaml").read_text(encoding="utf-8")
        (root / ".okf/config.yaml").write_text(tmpl, encoding="utf-8")
        project = self.project(root)
        self.assertEqual(project.config_issues, [])
        self.assertEqual(project.config["brain"]["tickets"], {"system": "none", "target": ""})

    def git_repo(self, root, *remotes):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for name, url in remotes:
            subprocess.run(["git", "-C", str(root), "remote", "add", name, url], check=True)

    def test_github_remotes(self):
        root = self.brain()
        self.git_repo(root, ("upstream", "https://github.com/acme/brain.git"), ("origin", "git@github.com:me/brain.git"),
                      ("other", "https://gitlab.com/acme/brain.git"), ("ssh", "ssh://git@github.com/acme/brain"))
        self.assertEqual(okf.github_remotes(root), ["me/brain", "acme/brain"])
        self.assertEqual(okf.github_remotes(self.tmp / "nowhere"), [])

    def test_gh_allowed_only_for_github_in_a_repo_with_a_github_remote(self):
        github = "  tickets:\n    system: github\n"
        root = self.brain(tickets=github)
        self.git_repo(root, ("origin", "https://github.com/acme/brain.git"))
        out = self.cli("context", cwd=root).stdout
        self.assertIn("no target set: suggest acme/brain, this repository's GitHub remote, and ask", out)
        self.assertIn("the gh CLI is allowed here (git repository with GitHub remote acme/brain)", out)
        rep = json.loads(self.cli("context", "--json", cwd=root).stdout)
        self.assertEqual(rep["brain"]["gh_cli"], "acme/brain")
        root = self.brain(tickets=github)  # no git repository
        out = self.cli("context", cwd=root).stdout
        self.assertIn("so the gh CLI isn't allowed", out)
        self.assertIsNone(json.loads(self.cli("context", "--json", cwd=root).stdout)["brain"]["gh_cli"])

    def test_gh_not_offered_for_other_systems_or_without_actions(self):
        root = self.brain()  # linear
        self.git_repo(root, ("origin", "https://github.com/acme/brain.git"))
        self.assertNotIn("gh CLI", self.cli("context", cwd=root).stdout)
        root = self.brain(tickets="  tickets:\n    system: github\n", actions_mode="off")
        self.git_repo(root, ("origin", "https://github.com/acme/brain.git"))
        out = self.cli("context", cwd=root).stdout
        self.assertNotIn("gh CLI", out)
        self.assertNotIn("- TICKETS:", out)
