"""The engine must not know what it is running inside.

This is the one test that keeps the architecture honest: Ti Matrix is an engine that other programs import,
not a feature of any of them. If a future change reaches for a host application's module, its vocabulary, or
its configuration "just this once", this fails before the coupling can spread.

Three rules, all host-neutral:
  1. the core imports nothing but the standard library and itself;
  2. the core imports none of its own adapters (the dependency runs one way: adapter -> engine);
  3. the core cites no external record system and reads no ambient configuration.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

import pytest

import ti_matrix  # locate the engine that is actually imported, not a checkout layout

ENGINE_ROOT = pathlib.Path(ti_matrix.__file__).resolve().parent
CORE_FILES = sorted(p for p in ENGINE_ROOT.rglob("*.py") if "adapters" not in p.parts)
ADAPTER_FILES = sorted(p for p in ENGINE_ROOT.rglob("*.py") if "adapters" in p.parts)
STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_engine_core_imports_nothing_but_the_standard_library_and_itself():
    forbidden: dict[str, list[str]] = {}
    for path in CORE_FILES:
        hits = sorted(_imported_roots(path) - STDLIB - {"ti_matrix"})
        if hits:
            forbidden[path.name] = hits
    assert not forbidden, f"the engine core depends on something outside the standard library: {forbidden}"


def test_the_engine_core_imports_none_of_its_own_adapters():
    offenders: dict[str, list[str]] = {}
    for path in CORE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ti_matrix.adapters")
        ]
        if hits:
            offenders[path.name] = hits
    assert not offenders, f"the engine core depends on an adapter: {offenders}"


def test_the_shipped_adapters_are_host_free():
    """An adapter brings an environment; it must not drag in a host application to do it."""
    assert ADAPTER_FILES, "expected the adapters package to ship at least one example"
    offenders: dict[str, list[str]] = {}
    for path in ADAPTER_FILES:
        hits = sorted(_imported_roots(path) - STDLIB - {"ti_matrix"})
        if hits:
            offenders[path.name] = hits
    assert not offenders, f"a shipped adapter needs a host installed: {offenders}"


# A host's record system and its configuration are dependencies too, even as prose: they tie the engine's
# readers (and its prompts) to another project's bookkeeping. Checked over every line, docstrings included.

EXTERNAL_RECORD_VOCABULARY = re.compile(
    r"\bADR-\d+|\bB-\d{4}-\d{2}-\d{2}-\d+|\.context_ledger|\bS\d{3}\b|\bSession \d+\b"
)


def test_the_engine_core_cites_no_external_record_system():
    offenders: dict[str, list[str]] = {}
    for path in CORE_FILES:
        hits = [
            f"{i}: {m.group(0)}"
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            for m in [EXTERNAL_RECORD_VOCABULARY.search(line)]
            if m
        ]
        if hits:
            offenders[path.name] = hits
    assert not offenders, f"the engine core cites an external record system: {offenders}"


def test_the_engine_core_reads_no_ambient_configuration():
    """No environment variables, no config files: a caller passes everything through the constructor."""
    offenders: dict[str, list[str]] = {}
    for path in CORE_FILES:
        text = path.read_text(encoding="utf-8")
        hits = [name for name in ("os.environ", "getenv", "environ[") if name in text]
        if hits:
            offenders[path.name] = hits
    assert not offenders, f"the engine core reads ambient configuration: {offenders}"


CORE_MODULES = [
    "ti_matrix",
    "ti_matrix.state",
    "ti_matrix.search",
    "ti_matrix.model",
    "ti_matrix.protocols",
    "ti_matrix.simulator",
    # the tool set and the learning layer are core too: their rules and their counters are the engine's,
    # and the persistence that makes them survive a run lives in adapters, where every other file does.
    "ti_matrix.tools",
    "ti_matrix.tools.registry",
    "ti_matrix.tools.composite",
    "ti_matrix.tools.engine_tools",
    "ti_matrix.learning",
    "ti_matrix.learning.statistics",
    "ti_matrix.learning.proposer",
    "ti_matrix.learning.cache",
]


@pytest.mark.parametrize("module", CORE_MODULES)
def test_every_core_module_imports_without_a_host_on_the_path(module):
    import importlib

    saved = {k: v for k, v in sys.modules.items() if k.startswith(("core", "ti_matrix", "api", "adapters"))}
    for k in list(saved):
        sys.modules.pop(k, None)
    try:
        importlib.import_module(module)
    finally:
        sys.modules.update(saved)
