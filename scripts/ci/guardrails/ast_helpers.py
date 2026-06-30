"""Shared AST helpers for CI guardrails."""

from __future__ import annotations

import ast


def extract_name_targets(node: ast.AST) -> set[str]:
    """Recursively extract all Name ID targets from a binding pattern."""
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Starred):
        names.update(extract_name_targets(node.value))
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            names.update(extract_name_targets(elt))
    return names
