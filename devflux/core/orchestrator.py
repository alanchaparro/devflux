"""Orchestrator — classifies intent, selects teams, determines complexity."""

from __future__ import annotations

from enum import Enum
from typing import Any


class Complexity(Enum):
    """Adaptive complexity levels (Lesson 12)."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


# Lesson 12: roles per complexity level
COMPLEXITY_ROLES: dict[Complexity, list[str]] = {
    Complexity.SIMPLE: ["analista", "arquitecto", "frontend"],
    Complexity.MEDIUM: ["analista", "arquitecto", "planificador", "backend", "frontend", "reviewer"],
    Complexity.COMPLEX: ["analista", "arquitecto", "planificador", "backend", "frontend", "qa", "reviewer", "integrador"],
}

# Lesson 12: token budget per complexity
COMPLEXITY_TOKENS: dict[Complexity, int] = {
    Complexity.SIMPLE: 2048,
    Complexity.MEDIUM: 4096,
    Complexity.COMPLEX: 8192,
}


# Keywords for intent classification
CREATE_KEYWORDS = {"crear", "hacer", "desarrollar", "construir", "generar", "armar", "montar", "build", "create", "make", "desarrollar una", "nuevo", "nueva"}
BUG_KEYWORDS = {"bug", "error", "no funciona", "falla", "fallando", "roto", "crashea", "excepción", "exception", "fix", "corregir", "arreglar", "broken"}
REPO_KEYWORDS = {"documentar", "analizar repo", "entender", "inventariar", "documentacion", "analize repo", "repo"}


class Orchestrator:
    """Decides which team(s) to run based on user input."""

    def __init__(self) -> None:
        self.teams: list[str] = []
        self.complexity: Complexity = Complexity.MEDIUM

    def classify(self, user_input: str) -> tuple[list[str], Complexity]:
        """Classify user intent. Returns (teams, complexity).

        Teams: 'dev', 'bugs', 'repo' or combinations.
        """
        text = user_input.lower().strip()

        # Determine team(s)
        teams: list[str] = []
        is_bug = any(kw in text for kw in BUG_KEYWORDS)
        is_create = any(kw in text for kw in CREATE_KEYWORDS)
        is_repo = any(kw in text for kw in REPO_KEYWORDS)

        if is_bug and is_create:
            # Feature in existing repo → dev + bugs
            teams = ["dev", "bugs"]
        elif is_bug:
            teams = ["bugs"]
        elif is_repo:
            teams = ["repo"]
        elif is_create:
            # Feature new → dev + bugs (auto review)
            teams = ["dev", "bugs"]
        else:
            # Ambiguous → default to dev
            teams = ["dev"]

        # Determine complexity
        word_count = len(text.split())
        has_search = any(kw in text for kw in ["buscador", "busqueda", "search", "login", "auth", "api", "base de datos", "database", "auth", "websocket"])
        has_multi_feature = text.count(" y ") >= 2 or text.count(" con ") >= 2

        if word_count < 10 and not has_search:
            complexity = Complexity.SIMPLE
        elif word_count > 30 or has_multi_feature or has_search:
            complexity = Complexity.COMPLEX
        else:
            complexity = Complexity.MEDIUM

        self.teams = teams
        self.complexity = complexity
        return teams, complexity

    def get_roles(self) -> list[str]:
        """Get the list of roles based on selected team(s) and complexity."""
        all_roles: list[str] = []
        for team in self.teams:
            if team == "dev":
                all_roles.extend(COMPLEXITY_ROLES[self.complexity])
            elif team == "bugs":
                all_roles.extend([
                    "bug-intake", "reproductor", "logs", "diagnostico",
                    "fixer", "regression-guard", "qa", "reviewer", "integrador",
                ])
            elif team == "repo":
                all_roles.extend(["repo-inventory", "repo-docs"])
        return all_roles

    def summary(self) -> str:
        """Human-readable summary of orchestration decision."""
        return (
            f"Equipos: {', '.join(self.teams)} | "
            f"Complejidad: {self.complexity.value} | "
            f"Roles: {len(self.get_roles())}"
        )