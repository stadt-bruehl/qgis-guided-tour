# SPDX-License-Identifier: GPL-2.0-or-later
"""List all translatable UI strings (tr("...") calls and helper labels) as JSON.

Usage: python3 tools/extract_strings.py
Then update i18n/guided_tour_<lang>.ts and run tools/build_translations.py.
"""
import ast
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def extract():
    found = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
        tree = ast.parse(open(path, encoding="utf-8").read())
        name = os.path.basename(path)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                found.setdefault(node.args[0].value, (name, node.lineno))
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "HELPERS" for t in node.targets):
                for v in node.value.values:
                    found.setdefault(v.elts[0].value, (name, v.lineno))
    return found


if __name__ == "__main__":
    print(json.dumps({k: list(v) for k, v in extract().items()}, ensure_ascii=False, indent=1))
