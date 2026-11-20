"""Command-line interface."""

import argparse
import json
from pathlib import Path

from migration_guard.analyzer import analyze


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check PostgreSQL migration SQL for common rollout risks"
    )
    parser.add_argument("file", type=Path, help="SQL migration file")
    parser.add_argument("--fail-on", choices=("error", "warning", "never"), default="error")
    args = parser.parse_args()
    try:
        result = analyze(args.file.read_text(encoding="utf-8"))
    except OSError as exc:
        parser.error(str(exc))
    print(json.dumps(result.to_dict(), indent=2))
    if args.fail_on == "error" and result.blocked:
        return 1
    if args.fail_on == "warning" and result.findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
