from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "backend" / "slaifi"
LOWER_LAYERS = {"core", "domain", "engines"}
ALLOWED = {"core": set(), "domain": {"core"}, "engines": {"core", "domain"}}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: modules.add(node.module)
    return modules


def test_lower_layers_obey_exact_dependency_direction() -> None:
    violations=[]
    for layer in sorted(LOWER_LAYERS):
        for path in (PACKAGE_ROOT/layer).rglob("*.py"):
            for module in _imports(path):
                if module.startswith("slaifi."):
                    target=module.split(".")[1]
                    if target != layer and target not in ALLOWED[layer]: violations.append(f"{path.relative_to(PACKAGE_ROOT)}: {layer} -> {target}")
    assert not violations, "\n".join(violations)


def test_lower_layer_dependency_graph_is_acyclic() -> None:
    graph: dict[str,set[str]]=defaultdict(set)
    for layer in LOWER_LAYERS:
        for path in (PACKAGE_ROOT/layer).rglob("*.py"):
            for module in _imports(path):
                if module.startswith("slaifi."):
                    target=module.split(".")[1]
                    if target in LOWER_LAYERS and target != layer: graph[layer].add(target)
    visiting:set[str]=set(); visited:set[str]=set()
    def visit(node:str)->None:
        if node in visiting: raise AssertionError(f"cycle detected at {node}")
        if node in visited: return
        visiting.add(node)
        for target in graph[node]: visit(target)
        visiting.remove(node); visited.add(node)
    for layer in LOWER_LAYERS: visit(layer)


def test_lower_layers_contain_no_cwd_or_sys_path_hacks() -> None:
    forbidden=("os.getcwd(","Path.cwd(","sys.path.append(","sys.path.insert(")
    violations=[]
    for layer in LOWER_LAYERS:
        for path in (PACKAGE_ROOT/layer).rglob("*.py"):
            text=path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text: violations.append(f"{path.relative_to(PACKAGE_ROOT)} contains {token}")
    assert not violations, "\n".join(violations)


def test_package_imports_from_external_working_directory(tmp_path: Path) -> None:
    applications=tmp_path/"SLAI"/"applications"; applications.mkdir(parents=True)
    env=os.environ.copy(); env["PYTHONPATH"]=str(PACKAGE_ROOT.parent)
    command=[sys.executable,"-c","from slaifi.domain.assets import AssetId; from slaifi.engines.risk import maximum_drawdown; assert AssetId('ABC').symbol == 'ABC'; assert abs(maximum_drawdown([100,80])+0.2)<1e-12"]
    subprocess.run(command,cwd=applications,env=env,check=True,capture_output=True,text=True)
