from __future__ import annotations

import pytest

from devflux.core.runner import extract_files, render_prompt, template_for_role


def test_routes_bug_and_repo_roles_to_specialized_templates() -> None:
    assert template_for_role("diagnostico") == "bugs/diagnostico.j2"
    assert template_for_role("repo-inventory") == "repo/inventory.j2"


def test_missing_template_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="Plantilla no encontrada"):
        render_prompt("bugs/no-existe.j2", user_input="test")


def test_extract_files_preserves_safe_nested_paths() -> None:
    files = extract_files(
        "Archivo: src/services/auth.py\n```python\nprint('auth service works')\n```",
        role="backend",
    )

    assert files == {"src/services/auth.py": "print('auth service works')"}


@pytest.mark.parametrize("filename", ["../secret.py", "/tmp/secret.py", "C:\\secret.py"])
def test_extract_files_rejects_unsafe_paths(filename: str) -> None:
    content = f"Archivo: {filename}\n```python\nprint('unsafe path content')\n```"

    assert extract_files(content, role="backend") == {}
