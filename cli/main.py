"""rolescan command line: one entry point for every platform-facing action."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "values", ROOT / "domain" / "ledger", ROOT / "domain" / "ats_registry", ROOT / "adapters"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from adapters import paths  # noqa: E402


def _doctor(args) -> int:
    from adapters import doctor
    return doctor.run(as_json=args.json, show_paths=args.paths)


def _setup(args) -> int:
    from adapters import setup
    return setup.run(browser=args.browser, python=args.python)


def _personas(args) -> int:
    from adapters import personas
    return personas.run()


def _poll(args) -> int:
    from adapters import ats_poll
    argv = ["--dry-run"] if args.dry_run else []
    return ats_poll.main(argv, root=paths.data_root(), out_dir=paths.data_root() / "drop")


def _ingest(args) -> int:
    import process_stream
    argv = []
    if args.once:
        argv += ["--once", str(args.once)]
    if args.fixtures:
        argv += ["--fixtures", str(args.fixtures)]
    if args.dry_run:
        argv.append("--dry-run")
    if args.filters:
        argv += ["--filters", str(args.filters)]
    if args.csv:
        argv += ["--csv", str(args.csv)]
    return process_stream.main(argv)


def _registry(args) -> int:
    from adapters import ats_registry_cli
    if args.registry_command == "show" and getattr(args, "json", False):
        import json
        from ats_registry import AtsRegistry
        registry = AtsRegistry()
        boards = registry.boards()
        by: dict[str, int] = {}
        for board in boards:
            by[board["ats"]] = by.get(board["ats"], 0) + 1
        print(json.dumps({"boards": len(boards), "by_ats": by, "emitted": len(registry.emitted())}))
        return 0
    argv = [args.registry_command]
    if args.registry_command == "seed" and args.file:
        argv += ["--file", args.file]
    if args.registry_command == "add":
        argv += [args.ats, args.tenant]
    return ats_registry_cli.main(argv)


def _selftest(args) -> int:
    from adapters import selftest
    return selftest.run()


def _sha256(args) -> int:
    if args.check:
        return _verify_checksums(Path(args.check))
    digest = hashlib.sha256(Path(args.file).read_bytes()).hexdigest()
    print(f"{digest}  {args.file}")
    return 0


def _verify_checksums(path: Path) -> int:
    rc = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        target = Path(name.strip())
        if not target.exists():
            print(f"SHA256:NOT_MET missing {target}")
            rc = 1
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            print(f"SHA256:NOT_MET {target}")
            rc = 1
        else:
            print(f"{target}: OK")
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rolescan", description="Role postings: setup, check, poll, ingest, notify.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="create venv, .env, filters/active.json")
    p.add_argument("--no-input", action="store_true", help="accepted for scripts; setup never prompts")
    p.add_argument("--browser", action="store_true", help="also install the browser dependencies")
    p.add_argument("--python", default=None, help="interpreter to build the venv with")
    p.set_defaults(func=_setup)

    p = sub.add_parser("doctor", help="readiness: CORE_READY plus optional rows")
    p.add_argument("--json", action="store_true")
    p.add_argument("--paths", action="store_true", help="also print interpreter, clone root and data root")
    p.set_defaults(func=_doctor)

    p = sub.add_parser("personas", help="four test users, offline, CSVs under data/results")
    p.set_defaults(func=_personas)

    p = sub.add_parser("poll", help="read the company boards once")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=_poll)

    p = sub.add_parser("ingest", help="ingest a batch and notify")
    p.add_argument("--once", type=Path)
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--filters", type=Path)
    p.add_argument("--csv", type=Path)
    p.set_defaults(func=_ingest)

    p = sub.add_parser("registry", help="company-board registry")
    rsub = p.add_subparsers(dest="registry_command", required=True)
    seed = rsub.add_parser("seed")
    seed.add_argument("--file", default=None)
    add = rsub.add_parser("add")
    add.add_argument("ats")
    add.add_argument("tenant")
    show = rsub.add_parser("show")
    show.add_argument("--json", action="store_true")
    p.set_defaults(func=_registry, file=None, ats=None, tenant=None)

    p = sub.add_parser("selftest", help="the offline gate: compile, secrets, docs, doctor, tests, fixture, tree")
    p.set_defaults(func=_selftest)

    p = sub.add_parser("sha256", help="hash a file, or verify a SHA256SUMS file")
    p.add_argument("file", nargs="?", default=None)
    p.add_argument("--check", default=None)
    p.set_defaults(func=_sha256)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as error:
        return int(error.code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
