"""Executable architecture rules for SLAIFI's Python package graph."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "backend" / "slaifi"

ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "core": set(),
    "domain": {"core"},
    "engines": {"core", "domain"},
    "application": {"core", "domain", "engines"},
    "infrastructure": {"core", "domain"},
    "integrations": {"core", "domain"},
    "api": {"core", "domain", "application"},
}


def _source_package(path: Path) -> str | None:
    relative = path.relative_to(PACKAGE_ROOT)
    if len(relative.parts) == 1:
        return None
    return relative.parts[0]


def _target_package(module_name: str) -> str | None:
    if not module_name.startswith("slaifi."):
        return None
    parts = module_name.split(".")
    return parts[1] if len(parts) > 1 else None


def _import_edges() -> set[tuple[str, str, Path]]:
    edges: set[tuple[str, str, Path]] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        source = _source_package(path)
        if source is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module_name in modules:
                target = _target_package(module_name)
                if target and target != source:
                    edges.add((source, target, path))
    return edges


def test_layer_dependencies_follow_allow_list() -> None:
    violations: list[str] = []
    for source, target, path in sorted(_import_edges(), key=lambda edge: str(edge[2])):
        allowed = ALLOWED_DEPENDENCIES.get(source)
        if allowed is not None and target not in allowed:
            relative = path.relative_to(PACKAGE_ROOT.parent)
            violations.append(f"{relative}: {source} -> {target} is forbidden")

    assert not violations, "\n".join(violations)


def test_internal_package_graph_is_acyclic() -> None:
    graph: dict[str, set[str]] = defaultdict(set)
    for source, target, _ in _import_edges():
        if source in ALLOWED_DEPENDENCIES and target in ALLOWED_DEPENDENCIES:
            graph[source].add(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in visiting:
            cycle = " -> ".join((*trail, node))
            raise AssertionError(f"circular SLAIFI package dependency detected: {cycle}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in sorted(graph[node]):
            visit(dependency, (*trail, node))
        visiting.remove(node)
        visited.add(node)

    for package in sorted(ALLOWED_DEPENDENCIES):
        visit(package, ())
