"""Static contract ensuring historical revisions never depend on current application schema."""

import ast
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
CHAIN = {
    "0001_identity_foundation.py": ("0001_identity_foundation", None),
    "0002_canonical_taxonomy.py": ("0002_canonical_taxonomy", "0001_identity_foundation"),
    "0003_sources_and_catalogue.py": (
        "0003_sources_and_catalogue",
        "0002_canonical_taxonomy",
    ),
    "0004_sync_and_audit.py": ("0004_sync_and_audit", "0003_sources_and_catalogue"),
}
PROHIBITED_TEXT = (
    "app.",
    "Base.metadata",
    ".__table__",
    ".create(",
    ".drop(",
    "create_all",
    "drop_all",
)


def assignments(tree: ast.Module) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                values[target.id] = ast.literal_eval(node.value)
    return values


@pytest.mark.parametrize(("filename", "expected"), CHAIN.items())
def test_revision_is_self_contained_and_explicit(
    filename: str, expected: tuple[str, str | None]
) -> None:
    source = (VERSIONS / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(pattern in source for pattern in PROHIBITED_TEXT)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module is None or not node.module.startswith("app")
        if isinstance(node, ast.Import):
            assert all(not alias.name.startswith("app") for alias in node.names)
    values = assignments(tree)
    assert (values["revision"], values["down_revision"]) == expected
    assert "op.create_table(" in source
    assert "op.drop_table(" in source


def test_revision_set_is_exactly_the_approved_chain() -> None:
    assert {path.name for path in VERSIONS.glob("*.py")} == set(CHAIN)
