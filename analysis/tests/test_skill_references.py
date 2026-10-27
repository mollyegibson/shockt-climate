"""Verify that the /analyze skill's reference files document exactly the public API they
describe. Fails when a function is added, removed or renamed in source but the reference
file was not updated — preventing silent drift."""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_REFS = REPO / ".claude" / "skills" / "analyze" / "references"
ANALYSIS_SRC = REPO / "analysis" / "src" / "shockt_analysis"
ENGINE_INIT = REPO / "engine" / "src" / "shockt_engine" / "__init__.py"


def _public_functions(path: Path) -> set[str]:
    """Return the names of public (non-underscore) top-level functions and classes."""
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
    return names


def _engine_all() -> set[str]:
    """Return every name in ``shockt_engine.__all__``."""
    tree = ast.parse(ENGINE_INIT.read_text())
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return {elt.value for elt in node.value.elts}  # type: ignore[union-attr]
    return set()


def _documented_names(path: Path, strip_prefix: str = "") -> set[str]:
    """Extract the function/class names from ``### `name(…)`` and ``### `ClassName`` headings.

    When *strip_prefix* is set (e.g. ``"cases."``), names starting with it are returned
    without the prefix so they match the source module's symbols.
    """
    text = path.read_text()
    raw = set(re.findall(r"###\s+`(\w[\w.]*)", text))
    if not strip_prefix:
        return raw
    result: set[str] = set()
    for name in raw:
        if name.startswith(strip_prefix):
            result.add(name[len(strip_prefix) :])
        else:
            result.add(name)
    return result


SKIP_CORE = {"connect"}
SKIP_CASES = {"git_commit", "write_derived"}


def test_data_access_documents_all_core_functions() -> None:
    source = _public_functions(ANALYSIS_SRC / "core.py") - SKIP_CORE
    documented = _documented_names(SKILL_REFS / "data-access.md")

    missing = source - documented
    extra = documented - source - SKIP_CORE
    assert not missing, f"core.py functions not in data-access.md: {sorted(missing)}"
    assert not extra, f"data-access.md documents functions not in core.py: {sorted(extra)}"


def test_engine_api_documents_all_engine_exports() -> None:
    source = _engine_all()
    documented = _documented_names(SKILL_REFS / "engine-api.md")
    engine_only = {n for n in documented if "." not in n}

    missing = source - engine_only
    extra = engine_only - source
    assert not missing, f"engine __all__ names not in engine-api.md: {sorted(missing)}"
    assert not extra, f"engine-api.md documents names not in engine __all__: {sorted(extra)}"


def test_engine_api_documents_all_cases_helpers() -> None:
    source = _public_functions(ANALYSIS_SRC / "cases.py") - SKIP_CASES
    documented = _documented_names(SKILL_REFS / "engine-api.md", strip_prefix="cases.")

    missing = source - documented
    extra_candidates = documented - source
    engine_names = _engine_all()
    extra = extra_candidates - engine_names
    assert not missing, f"cases.py functions not in engine-api.md: {sorted(missing)}"
    assert not extra, f"engine-api.md documents names not in cases.py or engine: {sorted(extra)}"
