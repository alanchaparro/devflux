"""Orchestrator — classifies intent, selects teams, determines complexity.

FEATURE 2: Intelligent orchestrator that classifies user intent BEFORE executing.
- Detects general questions and responds directly (no pipeline needed)
- Classifies code requests into teams (dev / bugs) and complexity levels
- Shows a preview of the decision before running
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class Complexity(Enum):
    """Adaptive complexity levels (Lesson 12)."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class IntentType(Enum):
    """What kind of request the user made."""
    CODE = "code"          # User wants code generated → run pipeline
    QUESTION = "question"  # User asks a general question → answer directly
    CHAT = "chat"          # Casual greeting/chat → respond directly


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
CREATE_KEYWORDS = {"crear", "hacer", "desarrollar", "construir", "generar", "armar", "montar", "build", "create", "make", "desarrollar una", "nuevo", "nueva", "codigo", "programa", "script", "clase", "componente", "pagina", "página", "app", "aplicacion", "aplicación", "web", "html", "css", "javascript", "react", "vue", "api", "endpoint"}
BUG_KEYWORDS = {"bug", "error", "no funciona", "falla", "fallando", "roto", "crashea", "excepción", "exception", "fix", "corregir", "arreglar", "broken", "no se ve", "no carga", "pantalla en blanco", "crash", "stacktrace", "traceback"}
REPO_KEYWORDS = {"documentar", "analizar repo", "entender", "inventariar", "documentacion", "analize repo", "repo"}

# Question detection keywords — if the input looks like a question, answer directly
QUESTION_KEYWORDS = {"?", "que es", "qué es", "como funciona", "cómo funciona", "que es", "explica", "explain", "que significa", "qué significa", "diferencia", "difference", "por que", "por qué", "why", "cuando", "cuándo", "when", "donde", "dónde", "where", "quien", "quién", "who"}

# Casual/chat detection
CHAT_KEYWORDS = {"hola", "hello", "hi", "buenas", "hey", "gracias", "thanks", "ok", "vale", "bien", "chau", "adios", "bye"}


class Orchestrator:
    """Decides which team(s) to run based on user input.

    FEATURE 2: Classifies intent first, then selects team and complexity.
    """

    def __init__(self) -> None:
        self.teams: list[str] = []
        self.complexity: Complexity = Complexity.MEDIUM
        self.intent: IntentType = IntentType.CODE
        self._roles: list[str] = []

    def classify_intent(self, user_input: str) -> IntentType:
        """Classify the high-level intent of the user input.

        Returns IntentType.CODE if the user wants code generated,
        IntentType.QUESTION if asking a general question,
        IntentType.CHAT for casual conversation.
        """
        text = user_input.lower().strip()

        # Check for casual/chat first (very short inputs with greetings)
        if len(text.split()) <= 3 and any(kw in text for kw in CHAT_KEYWORDS):
            return IntentType.CHAT

        # Check for question patterns
        # If the input ends with ? and is short, it's likely a question
        if text.endswith("?") and len(text.split()) < 20:
            # But if it contains code-generation keywords, it's still a code request
            if not any(kw in text for kw in CREATE_KEYWORDS | BUG_KEYWORDS):
                return IntentType.QUESTION

        # Check for question keywords at the start
        first_words = " ".join(text.split()[:4])
        if any(kw in first_words for kw in QUESTION_KEYWORDS):
            # But if it also has create/bug keywords, it's a code request
            has_code = any(kw in text for kw in CREATE_KEYWORDS)
            has_bug = any(kw in text for kw in BUG_KEYWORDS)
            if not has_code and not has_bug:
                return IntentType.QUESTION

        # Default: it's a code request
        return IntentType.CODE

    def classify(self, user_input: str) -> tuple[list[str], Complexity]:
        """Classify user intent. Returns (teams, complexity).

        Teams: 'dev', 'bugs', 'repo' or combinations.
        """
        text = user_input.lower().strip()

        # Reset state (BUG 1 fix: clear previous classification state)
        self.teams = []
        self.complexity = Complexity.MEDIUM
        self._roles = []

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
        # Pre-compute roles so get_roles() is deterministic
        self._roles = self._compute_roles()
        return teams, complexity

    def _compute_roles(self) -> list[str]:
        """Compute the list of roles based on current team(s) and complexity."""
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

    def get_roles(self) -> list[str]:
        """Get the list of roles based on selected team(s) and complexity."""
        # Return pre-computed roles if available, else compute fresh
        if self._roles:
            return list(self._roles)
        return self._compute_roles()

    def preview(self) -> str:
        """FEATURE 2: Show a preview of the orchestration decision before executing.

        Format: 'Equipo: dev | Complejidad: SIMPLE | 3 roles'
        """
        if not self.teams:
            return "(sin clasificar)"
        roles = self.get_roles()
        return (
            f"Equipo: {', '.join(self.teams)} | "
            f"Complejidad: {self.complexity.value.upper()} | "
            f"{len(roles)} roles"
        )

    def summary(self) -> str:
        """Human-readable summary of orchestration decision."""
        if not self.teams:
            return "(sin clasificar)"
        roles = self.get_roles()
        return (
            f"Equipos: {', '.join(self.teams)} | "
            f"Complejidad: {self.complexity.value} | "
            f"Roles: {len(roles)}"
        )