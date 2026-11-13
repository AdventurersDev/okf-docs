"""Check what eval runs wrote against the official OKF validator.

    python3 tests/okf_conformance.py --validator <validate.py> [--python <python with PyYAML>] <kept folder>...

A kept folder is one that `claude plugin eval --keep-temp` printed ("kept temp: ..."). The run's workspace
(sealed/home/cwd) is copied without .git into a temporary folder, so nothing runs inside the kept folder.
Every bundle in the workspace's .okf/config.yaml goes to the validator with --strict. Exit 1 if any bundle
has errors or warnings. TESTING.md says where to get the validator.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "okf-docs" / "skills" / "okf-docs" / "scripts"))
import okf  # noqa: E402


def workspace(kept):
    """The run's workspace inside a kept folder, unsealing it the way the eval tool says to."""
    for d in (kept, kept / "sealed"):
        if d.is_dir():
            os.chmod(str(d), 0o700)
    for cand in (kept / "sealed" / "home" / "cwd", kept / "home" / "cwd"):
        if cand.is_dir():
            return cand
    return None


def validate(python, validator, bundle):
    r = subprocess.run([python, "-I", str(validator), "--json", "--strict", str(bundle)], capture_output=True,
                       text=True, encoding="utf-8", timeout=120)
    try:
        findings = json.loads(r.stdout)
        if isinstance(findings, dict):
            findings = findings.get("findings", [])
    except ValueError:
        return r.returncode, [{"level": "error", "code": "validator", "message": (r.stderr or r.stdout).strip()}]
    return r.returncode, [f for f in findings if f.get("level") in ("error", "warning")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--validator", required=True, help="path to the OKF repo's skills/okf-generate/scripts/validate.py")
    ap.add_argument("--python", default=sys.executable, help="a Python with PyYAML for the validator")
    ap.add_argument("kept", nargs="+", type=Path)
    args = ap.parse_args(argv)
    failed, checked = 0, 0
    for kept in args.kept:
        ws = workspace(kept)
        if ws is None:
            print("SKIP %s: no workspace (sealed/home/cwd)" % kept)
            continue
        with tempfile.TemporaryDirectory(prefix="okf-conformance-") as tmp:
            copy = Path(tmp) / "ws"
            shutil.copytree(str(ws), str(copy), ignore=shutil.ignore_patterns(".git"), symlinks=True)
            config, _ = okf.Project.locate(copy)
            if config is None:
                print("SKIP %s: no .okf/config.yaml" % kept)
                continue
            project = okf.Project.load(config.parent.parent, config)
            for b in project.bundles:
                if not b.exists:
                    continue
                checked += 1
                code, problems = validate(args.python, args.validator, b.root)
                status = "ok" if code == 0 and not problems else "FAIL"
                print("%s %s %s" % (status, kept.name, b.rel.rstrip("/") + "/"))
                for f in problems:
                    print("    %s %s %s: %s" % (f.get("level"), f.get("path", ""), f.get("code", ""), f.get("message", "")))
                failed += status == "FAIL"
    print("%d bundles checked, %d failed" % (checked, failed))
    return 1 if failed or not checked else 0


if __name__ == "__main__":
    sys.exit(main())
