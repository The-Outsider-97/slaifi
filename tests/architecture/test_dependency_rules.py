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
    "integrations": {"core", "domain", "application"},
    "api": {"core", "domain", "application"},
}


def _source_package(path: Path) -> str | None:
    relative = path.relative_to(PACKAGE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else None


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


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
        for module_name in _imports(path):
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


def test_integrations_depend_only_on_application_contracts() -> None:
    violations: list[str] = []
    root = PACKAGE_ROOT / "integrations"
    for path in root.rglob("*.py"):
        for module in _imports(path):
            if module == "slaifi.application":
                violations.append(f"{path}: broad application import is forbidden")
            elif module.startswith("slaifi.application.") and not module.startswith(
                "slaifi.application.contracts"
            ):
                violations.append(f"{path}: integration imports use case {module}")
    assert not violations, "\n".join(violations)


def test_api_does_not_import_integrations_or_infrastructure() -> None:
    violations: list[str] = []
    for path in (PACKAGE_ROOT / "api").rglob("*.py"):
        for module in _imports(path):
            if module.startswith(("slaifi.integrations", "slaifi.infrastructure")):
                violations.append(f"{path}: API imports {module}")
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
            raise AssertionError("circular dependency: " + " -> ".join((*trail, node)))
        if node in visited:
            return
        visiting.add(node)
        for dependency in sorted(graph[node]):
            visit(dependency, (*trail, node))
        visiting.remove(node)
        visited.add(node)

    for package in sorted(ALLOWED_DEPENDENCIES):
        visit(package, ())
