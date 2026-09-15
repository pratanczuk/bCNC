#!/usr/bin/env python3
"""Read-only candidate report. Never deletes code or proves dynamic reachability.

Attribute loads, imported names and literal callback names count as references.
Self-recursion, runtime-generated names and inheritance require human review.
Run from any directory; --include-libraries includes bundled utility methods.
"""
import argparse
import ast
from collections import Counter
from pathlib import Path


def candidates(root, include_libraries=False):
    references = Counter()
    definitions = []
    for path in sorted(root.rglob('*.py')):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                references[node.attr] += 1
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references[node.id] += 1
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                references[node.value] += 1
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    references[alias.name] += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.append((path, node.lineno, node.name))
    return [(path, line, name) for path, line, name in definitions
            if not references[name] and not name.startswith('__')
            and (include_libraries or 'lib' not in path.relative_to(root).parts)]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-libraries', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'bCNC'
    for path, line, name in candidates(root, args.include_libraries):
        print(f'{path.relative_to(root.parent)}:{line}: {name}')
