"""Orchestrator — classifies intent, selects teams, determines complexity.

FEATURE 2: Intelligent orchestrator that classifies user intent BEFORE executing.
- Detects general questions and responds directly (no pipeline needed)
- Classifies code requests into teams (dev / bugs) and complexity levels
- Shows a preview of the decision before running

REFACTOR: classify_intent() now uses LLM instead of keyword matching.
The LLM receives the user text and responds CODE, QUESTION or CHAT.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import LLMClient


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

# Keywords for team selection (used by classify() — NOT by classify_intent())
CREATE_KEYWORDS = {"crear", "hacer", "desarrollar", "construir", "generar", "armar", "montar", "build", "create", "make", "desarrollar una", "nuevo", "nueva", "codigo", "programa", "script", "clase", "componente", "pagina", "página", "app", "aplicacion", "aplicación", "web", "html", "css", "javascript", "react", "vue", "api", "endpoint"}
BUG_KEYWORDS = {"bug", "error", "no funciona", "falla", "fallando", "roto", "crashea", "excepción", "exception", "fix", "corregir", "arreglar", "broken", "no se ve", "no carga", "pantalla en blanco", "crash", "stacktrace", "traceback"}
REPO_KEYWORDS = {"documentar", "analizar repo", "entender", "inventariar", "documentacion", "analize repo", "repo"}

# NOTE: QUESTION_KEYWORDS and CHAT_KEYWORDS removed — intent classification now uses LLM.


# System prompt for LLM-based intent classification
_CLASSIFY_SYSTEM_PROMPT = (
    "Sos un clasificador de intenciones. El usuario escribio un mensaje. "
    "Clasifica en una de 3 categorias:\n"
    "- CODE: el usuario quiere generar, crear, modificar o corregir codigo\n"
    "- QUESTION: el usuario hace una pregunta sobre el proyecto, tecnologia, "
    "concepto, o quiere una explicacion\n"
    "- CHAT: saludo casual, agradecimiento, o mensaje corto sin intencion clara\n"
    "Respondi con UNA sola palabra: CODE, QUESTION o CHAT"
)


class Orchestrator:
    """Decides which team(s) to run based on user input.

    FEATURE 2: Classifies intent first, then selects team and complexity.
    REFACTOR: Intent classification now uses LLM instead of keyword matching.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.teams: list[str] = []
        self.complexity: Complexity = Complexity.MEDIUM
        self.intent: IntentType = IntentType.CODE
        self._roles: list[str] = []
        self._llm_client: LLMClient | None = llm_client

    def classify_intent(self, user_input: str) -> IntentType:
        """Classify the high-level intent of the user input using LLM.

        Returns IntentType.CODE if the user wants code generated,
        IntentType.QUESTION if asking a general question,
        IntentType.CHAT for casual conversation.

        Falls back to IntentType.CODE on any error (better to run pipeline than do nothing).
        """
        if self._llm_client is None:
            # No LLM client available — default to CODE
            return IntentType.CODE

        messages = [
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        try:
            response = self._llm_client.chat(
                messages,
                temperature=0,
                max_tokens=10,
            )
        except Exception:
            # On any error, default to CODE (better to run pipeline than do nothing)
            return IntentType.CODE

        # Parse the response — should be a single word
        raw = response.content.strip().upper() if response.content else ""

        # Accept the word anywhere in the response (in case LLM adds punctuation)
        if "CODE" in raw:
            return IntentType.CODE
        elif "QUESTION" in raw:
            return IntentType.QUESTION
        elif "CHAT" in raw:
            return IntentType.CHAT
        else:
            # Unrecognized response — default to CODE
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
