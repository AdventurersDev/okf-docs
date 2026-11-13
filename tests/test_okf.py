"""Tests for the okf-docs helper script. Run from the repository root:

    python3 -m unittest discover tests

The fixtures live in okf-docs/evals/fixtures/, shared with the plugin's eval suite. They are copied
to a temporary folder for each test, with a private HOME, so tests never touch the fixtures or your
own settings. Git tests are skipped when git isn't installed.
"""

from __future__ import annotations

import datetime as dt
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
class: observation
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
            "generated": {"by": "okf-docs/0.9.1", "at": "2026-11-12T14:03:22+01:00"},
            "verified": [{"by": "human:alex", "at": "2026-11-12T16:40:00+01:00"}],
            "sources": [{"id": "job", "resource": "../../src/export/job.ts"},
                        {"resource": "https://example.com/x?a=1"}],
            "nested": {"deep": {"list": [[1, 2], {"k": "v"}], "text": "line one\nline two\n"}},
            "empty_list": [], "empty_map": {}, "version": "0.2", "colon_end": "Note:", "dash": "- not a list",
        }
        text = "\n".join(okf.yaml_dump(data)) + "\n"
        back, warnings = okf.yaml_load(text)
        self.assertEqual(back, data)
        self.assertEqual(warnings, [])
        self.assertIn("generated:\n  by: okf-docs/0.9.1\n  at: 2026-11-12T14:03:22+01:00\n", text)
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
        self.assertEqual(okf.parse_ts("2026-11-12")[1], okf.DATE_ONLY)
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
        for expected in [("docs/index.md", "index-frontmatter"), ("docs/product/index.md", "index-frontmatter"),
                         ("docs/product/invoices.md", "timestamp-format"),
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

    def test_missing_frontmatter(self):
        root = self.fixture("repo")
        (root / "docs/product/notes.md").write_text("# Notes\n\nNo frontmatter.\n", encoding="utf-8")
        (root / "docs/README.md").write_text("# Docs\n", encoding="utf-8")
        found = {f.path: f for f in self.findings(root) if f.code == "fm-missing"}
        self.assertEqual(set(found), {"docs/product/notes.md", "docs/README.md"})
        self.assertEqual(found["docs/product/notes.md"].severity, "error")
        self.assertIn("README.md inside a bundle", found["docs/README.md"].message)

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
        self.assertEqual((root / "docs/index.md").read_text(encoding="utf-8").split("---")[1].strip(), 'okf_version: "0.2"')
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
        self.assertTrue(top.startswith('---\nokf_version: "0.2"\n---\n'))
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
        self.assertIsNone(okf._upgrade_actor("okf-docs/0.9.1"))

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

    def test_credibility_is_kept_and_ranks_trust(self):
        root = self.fixture("repo")
        page = root / "docs/system/architecture.md"
        text = page.read_text(encoding="utf-8")
        for cred, trust in (("reported", "reported"), ("inferred", "inferred")):
            page.write_text(text.replace("type: design\n", "type: design\ncredibility: %s\n" % cred, 1),
                            encoding="utf-8")
            doc = okf.Doc.load(self.project(root).bundle_for(page), page)
            self.assertEqual(doc.trust(), trust)
            self.assertFalse(okf.is_v3(doc))
            self.assertIn("changed 0 files", self.cli("upgrade", cwd=root).stdout)
            self.assertIn("credibility: %s" % cred, page.read_text(encoding="utf-8"))
        codes = {(f.path, f.code) for f in self.findings(root)}
        self.assertNotIn(("docs/system/architecture.md", "enum-value"), codes)

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
        page.write_text(page.read_text(encoding="utf-8").replace("credibility: reported", "status: draft"),
                        encoding="utf-8")
        self.assertIn(("help/export-your-data.md", "draft"), {(f.path, f.code) for f in self.findings(root)})

    def test_index_holding_a_page_is_never_rewritten(self):
        root = self.fixture("brain-repo")
        bundle = self.project(root).bundles[0]
        page = self.write(bundle.root / "products/waycam/index.md",
                          "---\nclass: canonical\ntype: product\ntitle: WayCam\ncredibility: reported\n---\n\n"
                          "# WayCam\n\n## What it is\n\nTurns a phone into a webcam.\n\n"
                          "## Who it serves\n\nPeople with a spare phone.\n\nFree to use while it builds traction.\n")
        self.write(bundle.root / "products/waycam/pricing.md",
                   "---\ntype: product\nclass: canonical\ntitle: WayCam pricing\ndescription: Free.\n---\n\n# Pricing\n")
        before = page.read_text(encoding="utf-8")
        rel = okf.relpath(page, root)
        self.assertIn((rel, "index-page"), {(f.path, f.code) for f in self.findings(root)})
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
        self.assertIn("okf-docs 0.9.1", self.cli("--version").stdout)
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
        self.assertIn("ACTOR human:tester (from OKF_ACTOR) · agent okf-docs/0.9.1", out)
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
        (root / "docs/product/broken.md").write_text("no frontmatter\n", encoding="utf-8")
        r = self.cli("check", "docs/product/broken.md", cwd=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fm-missing", r.stdout)

    def test_now_and_log(self):
        root = self.fixture("repo")
        out = self.cli("now", cwd=root).stdout
        self.assertIn("human: human:tester", out)
        self.assertIn("agent: okf-docs/0.9.1", out)
        r = self.cli("log", "docs", "Update", "Changed", "data-export.md.", cwd=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("* **Update**: Changed data-export.md.", (root / "docs/log.md").read_text(encoding="utf-8"))

    def test_lint_and_find_output(self):
        root = self.fixture("repo")
        out = self.cli("lint", "docs", cwd=root).stdout
        self.assertIn("data-export.md", out)
        out = self.cli("find", "export", "--json", cwd=root).stdout
        self.assertTrue(json.loads(out))


if __name__ == "__main__":
    unittest.main()
