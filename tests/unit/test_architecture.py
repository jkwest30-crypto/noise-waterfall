"""Machine-enforced architecture invariants.

An agent's opinion is not a guardrail. A failing test is. These cover
invariants 1, 2 and 4 from the plan; mypy --strict covers 5, and invariants
3 and 6 have their own dedicated tests.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = SRC / "waterfall"

LAYER_RANK = {"domain": 0, "engine": 1, "api": 2}

# domain/ is the science. numpy for array math and nothing else: no web
# framework, no I/O, no serialization library, no knowledge of the browser.
DOMAIN_ALLOWED_THIRD_PARTY = {"numpy"}

# Holding numbers is the entire job of these files, so invariant 4 exempts them.
NUMERIC_LITERAL_EXEMPT = {"constants.py", "cie1931_data.py"}

# Structural numbers carrying no physical meaning: indices, small counts, and
# the identity/zero elements that appear in ordinary array code.
ALLOWED_INTS = frozenset({0, 1, 2, 3})
ALLOWED_FLOATS = frozenset({0.0, 0.5, 1.0, 2.0})


def python_files() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if p.name != "__init__.py")


def all_files() -> list[Path]:
    return sorted(PKG.rglob("*.py"))


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def layer_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "waterfall" and parts[1] in LAYER_RANK:
        return parts[1]
    return None


def imported_modules(path: Path) -> set[str]:
    """Absolute module names imported by `path`, with relative imports resolved."""
    tree = ast.parse(path.read_text(), filename=str(path))
    own = module_name(path)
    package = own.rsplit(".", 1)[0] if "." in own else own
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                # level 1 means "this package"; each extra level walks up one.
                trimmed = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                prefix = ".".join(trimmed)
                found.add(f"{prefix}.{node.module}" if node.module else prefix)
            elif node.module:
                found.add(node.module)
    return found


def root_of(module: str) -> str:
    return module.split(".")[0]


def test_scanner_actually_finds_the_package() -> None:
    """Guard against every other test in this file passing vacuously.

    If the glob or the src layout ever breaks, these invariant tests would
    silently scan nothing and report green. That failure mode is worse than
    having no tests at all, so it gets its own assertion.
    """
    assert PKG.is_dir(), f"package not found at {PKG}"
    assert all_files(), "no python files discovered - the scanner is broken"


def test_domain_imports_only_numpy_and_stdlib() -> None:
    """Invariant 1: the domain layer stays pure and framework-free."""
    violations: list[str] = []

    for path in python_files():
        if layer_of(module_name(path)) != "domain":
            continue
        for imported in imported_modules(path):
            root = root_of(imported)
            if root == "waterfall":
                continue
            if root in sys.stdlib_module_names:
                continue
            if root in DOMAIN_ALLOWED_THIRD_PARTY:
                continue
            violations.append(f"{module_name(path)} imports {imported}")

    assert not violations, "domain/ must import only numpy and stdlib:\n" + "\n".join(
        violations
    )


def test_layer_dependencies_point_inward() -> None:
    """Invariant 2: api -> engine -> domain, never the reverse."""
    violations: list[str] = []

    for path in python_files():
        own = module_name(path)
        own_layer = layer_of(own)
        if own_layer is None:
            continue
        for imported in imported_modules(path):
            other_layer = layer_of(imported)
            if other_layer is None:
                continue
            if LAYER_RANK[other_layer] > LAYER_RANK[own_layer]:
                violations.append(f"{own} ({own_layer}) imports {imported} ({other_layer})")

    assert not violations, "dependencies must point inward:\n" + "\n".join(violations)


def test_no_import_cycles() -> None:
    """Invariant 2, continued: cycles inside a layer fail the build too."""
    graph: dict[str, set[str]] = {}
    for path in all_files():
        own = module_name(path)
        graph[own] = {m for m in imported_modules(path) if root_of(m) == "waterfall"}

    visiting: set[str] = set()
    done: set[str] = set()
    cycles: list[str] = []

    def walk(node: str, trail: list[str]) -> None:
        if node in done:
            return
        if node in visiting:
            start = trail.index(node)
            cycles.append(" -> ".join(trail[start:] + [node]))
            return
        visiting.add(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt in graph:
                walk(nxt, trail + [nxt])
        visiting.discard(node)
        done.add(node)

    for module in sorted(graph):
        walk(module, [module])

    assert not cycles, "import cycles detected:\n" + "\n".join(cycles)


def test_physical_constants_live_in_constants_module() -> None:
    """Invariant 4: no physical-quantity literal outside constants.py.

    Catches the drift where 380.0 or 3.0103 gets inlined at a call site and
    then silently disagrees with the same number elsewhere.
    """
    violations: list[str] = []

    for path in python_files():
        if layer_of(module_name(path)) != "domain":
            continue
        if path.name in NUMERIC_LITERAL_EXEMPT:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            value = node.value
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and value not in ALLOWED_INTS:
                violations.append(f"{path.name}:{node.lineno} bare int {value}")
            elif isinstance(value, float) and value not in ALLOWED_FLOATS:
                violations.append(f"{path.name}:{node.lineno} bare float {value}")

    assert not violations, (
        "physical constants belong in domain/constants.py:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize("layer", sorted(LAYER_RANK))
def test_every_layer_exists(layer: str) -> None:
    assert (PKG / layer).is_dir(), f"missing layer directory: {layer}"
