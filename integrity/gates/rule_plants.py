"""Every adopted rule is enforced (adrs/0008).

rules/enforced_by.json names, per rule in rules/adopted.json, the command
that enforces it and a planted violation. For each rule this copies the repo
to a temp dir, checks the plant's anchor exists (a plant that silently does
nothing would be a false green), runs the command on the clean copy (must
pass), applies the plant and runs it again (must fail). Prints
RULE_PLANTS:MET n/n, or NOT_MET with the reasons, and exits nonzero.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
HUB = os.environ.get("NLC_HUB", str(Path.home() / ".local/share/nlc/hub"))
PY = str(ROOT / "venv" / "bin" / "python") if (ROOT / "venv" / "bin" / "python").exists() else sys.executable
OPT = "autojob/automated-resume-optimizer"
SKIP = shutil.ignore_patterns("venv", "node_modules", ".git", "jobs_*.json", "watch", "downloads", "__pycache__",
                              "debug-*", "screenshot*", "downloaded_files", "mobs")


def run(cmd, cwd):
    cmd = [c.replace("{hub}", HUB).replace("{py}", PY) for c in cmd]
    # no bytecode cache: a same-size plant written in the same second as the
    # clean run's .pyc would otherwise run the old code and pass (2026-10-06)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, env=env)
    return r.returncode, (r.stdout + r.stderr)[-300:]


def main():
    rules = [a["rule_id"] for a in json.loads((ROOT / "rules/adopted.json").read_text())["adoptions"]]
    table = json.loads((ROOT / "rules/enforced_by.json").read_text())
    bad = [f"{r}: no entry in rules/enforced_by.json" for r in rules if r not in table]
    bad += [f"{r}: entry for a rule that is not adopted" for r in table if r not in rules]
    node_ok = (ROOT / OPT / "node_modules").is_dir() and shutil.which("node")
    met = 0
    not_run = []
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "repo"
        shutil.copytree(ROOT, copy, ignore=SKIP, symlinks=True)
        if (ROOT / "venv").exists():
            os.symlink(ROOT / "venv", copy / "venv")
        if node_ok:
            os.symlink(ROOT / OPT / "node_modules", copy / OPT / "node_modules")
        for rule in rules:
            entry = table.get(rule)
            if not entry:
                continue
            if entry["plant"]["file"].startswith("autojob/") or entry["cmd"][0] == "node":
                if not node_ok:
                    print(f"  {rule}: NOT_RUN (autojob submodule or node absent)")
                    not_run.append(rule)
                    continue
            cwd = copy / entry.get("cwd", ".")
            target = copy / entry["plant"]["file"]
            original = target.read_text()
            anchor = entry["plant"]["anchor"]
            if original.count(anchor) != 1:
                bad.append(f"{rule}: plant anchor found {original.count(anchor)} times in {entry['plant']['file']}")
                continue
            code, out = run(entry["cmd"], cwd)
            if code != 0:
                bad.append(f"{rule}: enforcing command fails on the clean tree: {out.strip()[-160:]}")
                continue
            planted = (original.replace(anchor, entry["plant"]["insert_before"] + anchor)
                       if "insert_before" in entry["plant"] else original.replace(anchor, entry["plant"]["replace"]))
            target.write_text(planted)
            try:
                code, out = run(entry["cmd"], cwd)
            finally:
                target.write_text(original)
            if code == 0:
                bad.append(f"{rule}: the planted violation passed its enforcing command")
            else:
                met += 1
                print(f"  {rule}: caught")
    for b in bad:
        print(f"VIOLATION {b}")
    tail = f" NOT_RUN {len(not_run)} (CI: private submodule; the fresh-clone gate runs them)" if not_run else ""
    print(f"RULE_PLANTS:{'MET' if not bad else 'NOT_MET'} {met}/{len(rules)}{tail}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
