from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .core import OdxInputError, compare, demo_paths
from .report import render


def _format(output: Path | None, requested: str | None) -> str:
    if requested:
        return requested
    if output:
        return {".html": "html", ".md": "markdown", ".markdown": "markdown", ".xml": "junit", ".sarif": "sarif"}.get(output.suffix.lower(), "json")
    return "json"


def _write(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
        os.replace(temporary, output)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gate a limited ODX/PDX diagnostic service contract")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare_cmd = commands.add_parser("compare", help="compare baseline and current ODX/PDX files or directories")
    compare_cmd.add_argument("baseline", type=Path)
    compare_cmd.add_argument("current", type=Path)
    demo_cmd = commands.add_parser("demo", help="run the packaged synthetic example")
    for command in (compare_cmd, demo_cmd):
        command.add_argument("--output", type=Path)
        command.add_argument("--format", choices=("json", "markdown", "html", "junit", "sarif"))
        command.add_argument("--fail-on", choices=("breaking", "any", "never"), default="breaking")
    args = parser.parse_args(argv)
    try:
        baseline, current = demo_paths() if args.command == "demo" else (args.baseline, args.current)
        if args.output:
            output = args.output.resolve()
            if output in {Path(baseline).resolve(), Path(current).resolve()}:
                raise OdxInputError("output must not overwrite an input ODX/PDX")
        report = compare([Path(baseline)], [Path(current)], args.fail_on)
        content = render(report, _format(args.output, args.format))
        if args.output:
            _write(args.output, content)
        else:
            print(content, end="")
        return 0 if report["passed"] else 1
    except (OdxInputError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
