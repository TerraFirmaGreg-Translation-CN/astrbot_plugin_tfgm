"""Reject releases whose tag, plugin metadata and registration version disagree."""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(tag, root=ROOT):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", tag):
        raise ValueError("Release tag must be vMAJOR.MINOR.PATCH or a prerelease tag")
    metadata = re.search(r"^version:\s*(\S+)\s*$", (root / "metadata.yaml").read_text(), re.M)
    if not metadata or metadata[1].strip("\"'") != tag:
        raise ValueError("Release tag must match metadata.yaml version")
    tree = ast.parse((root / "main.py").read_text())
    versions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "register"
                    and len(decorator.args) >= 4
                ):
                    versions.append(ast.literal_eval(decorator.args[3]))
    if versions != [tag[1:]]:
        raise ValueError("Release tag must match main.py @register version")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/check_release.py v0.3.0")
    try:
        validate(sys.argv[1])
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"Release version verified: {sys.argv[1]}")
