"""Orchestrator — classifies intent, selects teams, determines complexity.

FEATURE 2: Intelligent orchestrator that classifies user intent BEFORE executing.
- Detects general questions and responds directly (no pipeline needed)
- Classifies code requests into teams (dev / bugs) and complexity levels
- Shows a preview of the decision before running

REFACTOR: classify_intent() now uses LLM instead of keyword matching.
The LLM receives the user text and responds CODE, QUESTION or CHAT.

BUG FIX: Added 5s timeout + heuristic fallback for classification.
The LLM was misclassifying questions like "que otras opciones de mejora le ves"
as CODE because "mejora" sounded like "mejorar codigo". Now:
- Improved system prompt with explicit examples
- 5s timeout prevents hanging on slow LLM responses
- Heuristic fallback: if text starts with question words -> QUESTION
- Debug logging to .devflux/debug_classify.txt
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import LLMClient


# Runtime diagnostics are application state, never project files. Tests may
# redirect this constant to an isolated directory.
RUNS_DIR = Path.home() / ".devflux" / "runs"


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


class ConversationRoute(Enum):
    """Intent selected by the conversational LLM router."""

    MODIFY = "MODIFY"
    BUG = "BUG"
    QUESTION = "QUESTION"
    CLARIFY = "CLARIFY"


@dataclass(frozen=True)
class RouterResult:
    """A valid router decision or an explicit, recoverable router failure."""

    route: ConversationRoute | None = None
    error: str | None = None


# Product invariant: every feature or modification follows the complete
# internal equipo-dev sequence. Complexity can tune model budgets, never skip a
# responsibility or replace the team with a single implementer.
DEV_EIGHT_ROLE_SEQUENCE = [
    "analista", "arquitecto", "planificador", "backend",
    "frontend", "qa", "reviewer", "integrador",
]
COMPLEXITY_ROLES: dict[Complexity, list[str]] = {
    complexity: list(DEV_EIGHT_ROLE_SEQUENCE) for complexity in Complexity
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
# KEY INSIGHT: The LLM confuses "mejora" with "mejorar codigo" — we need explicit
# examples showing that opinion/analysis questions are QUESTION, not CODE.
_CLASSIFY_SYSTEM_PROMPT = (
    "Sos un clasificador de intenciones. El usuario escribio un mensaje. "
    "Clasifica en UNA de 3 categorias:\n\n"
    "CODE: SOLO si el usuario pide EXPLICITAMENTE que generes, crees, escribas, "
    "construyas, programes, codifiques, desarrolles, armes, o corrijas codigo. "
    "Ejemplos CODE:\n"
    '  - "crea un componente de login en React"\n'
    '  - "haceme una API REST con FastAPI"\n'
    '  - "genera el codigo para un carrito de compras"\n'
    '  - "corregi el bug del formulario de contacto"\n'
    '  - "escribi un script que procese CSV"\n\n'
    "QUESTION: el usuario PREGUNTA, pide opinion, analisis, explicacion, "
    "o quiere entender algo. NO pide que generes codigo. "
    "Ejemplos QUESTION:\n"
    '  - "que otras opciones de mejora le ves?"\n'
    '  - "que mejoras le harias a este codigo?"\n'
    '  - "que te parece esta arquitectura?"\n'
    '  - "como funciona el patron observer?"\n'
    '  - "cual es la diferencia entre async y sync?"\n'
    '  - "por que usaste Redis en vez de RabbitMQ?"\n'
    '  - "que opinas de este diseno?"\n'
    '  - "hay algo que mejorarias?"\n\n'
    "CHAT: saludo casual, agradecimiento, despedida, o mensaje sin intencion "
    "tecnica clara.\n"
    '  - "hola", "gracias", "chau", "buen trabajo"\n\n'
    "REGLA DE ORO: Si el mensaje empieza con 'que', 'cual', 'como', 'por que' "
    "y NO contiene un verbo de creacion (crea, hace, genera, construi, codifica, "
    "programa, escribi, desarrolla, arma), es QUESTION.\n\n"
    "Respondi EXACTAMENTE con UNA sola palabra: CODE, QUESTION o CHAT. "
    "Nada mas. Sin puntuacion. Sin explicacion."
)

_CONVERSATION_ROUTER_SYSTEM_PROMPT = """Sos el router conversacional de DevFlux para un proyecto existente.
Tu tarea es elegir el hilo correcto usando TODA la conversación, el hilo activo,
el contexto del proyecto y el último mensaje. No clasifiques por palabras aisladas.

Devolvé exclusivamente JSON válido: {\"route\": \"MODIFY|BUG|QUESTION|CLARIFY\"}.

MODIFY: hay una modificación implementable sobre archivos o proyecto existentes,
aunque no use verbos técnicos. Ejemplos obligatorios: "que el fondo tenga burbujas
animadas", "que al clicar cambie de color", "poné música", "ahora quiero que sea
más oscuro". Si el hilo activo es modify y el nuevo mensaje concreta el pedido,
es MODIFY.
BUG: describe un error o comportamiento roto concreto.
QUESTION: pide información, opinión o explicación sin pedir un cambio.
CLARIFY: únicamente si no hay objetivo implementable ni pregunta contestable;
ejemplo: "quiero continuar" sin detalle.
Nunca uses CLARIFY solo porque falte un verbo técnico. Nunca agregues explicación,
markdown ni otras claves al JSON."""


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

    @staticmethod
    def is_bug_request(user_input: str) -> bool:
        """Return whether a request explicitly describes a bug or error."""
        text = user_input.lower()
        return any(keyword in text for keyword in BUG_KEYWORDS)

    def select_user_action(self, user_input: str, action: str) -> tuple[list[str], Complexity, list[str]]:
        """Choose the internal team without exposing implementation choices.

        A create/modify request always uses the faithful eight-role equipo-dev
        chain. Explicit bugs retain their separate equipo-bugs route.
        """
        if action in {"create", "modify"}:
            self.teams = ["dev"]
            # Keep a proportional token budget, but never shorten the role chain.
            _teams, self.complexity = self.classify(user_input)
            self.teams = ["dev"]
            self._roles = list(DEV_EIGHT_ROLE_SEQUENCE)
            return self.teams, self.complexity, list(self._roles)

        team = "bugs" if action == "bugs" else "dev"
        teams, complexity = self.select_team(user_input, team)
        return teams, complexity, self.get_roles()

    def select_team(self, user_input: str, team: str) -> tuple[list[str], Complexity]:
        """Classify complexity, then force the confirmation-selected team."""
        _teams, complexity = self.classify(user_input)
        self.teams = [team]
        self._roles = self._compute_roles()
        return self.teams, complexity

    def route_conversation(
        self,
        conversation: list[dict[str, str]],
        active_thread: str,
        project_context: str,
        latest_user_message: str,
    ) -> RouterResult:
        """Route a turn using the entire thread; never fall back to keywords."""
        if self._llm_client is None:
            self._debug_log_classify(
                latest_user_message,
                "ROUTER ERROR: no hay cliente LLM configurado",
                "ERROR",
            )
            return RouterResult(error="No hay cliente LLM configurado para el router.")

        transcript = json.dumps(conversation, ensure_ascii=False)
        context = (
            f"HILO ACTIVO: {active_thread}\n\n"
            f"CONTEXTO DEL PROYECTO:\n{project_context}\n\n"
            f"CONVERSACIÓN COMPLETA (orden cronológico):\n{transcript}\n\n"
            f"ÚLTIMO MENSAJE DEL USUARIO:\n{latest_user_message}"
        )
        try:
            response = self._llm_client.chat(
                [
                    {"role": "system", "content": _CONVERSATION_ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
                temperature=0,
                # Reasoning-capable providers can spend the first tokens on
                # hidden analysis; 32 truncated the observed real response
                # before its required JSON decision. Keep this bounded while
                # leaving room for the final route.
                max_tokens=128,
                timeout=10,
            )
        except Exception as exc:
            self._debug_log_classify(latest_user_message, f"ROUTER ERROR: {exc}", "ERROR")
            return RouterResult(error=f"No se pudo decidir el hilo: {exc}")

        parts = self._router_response_parts(response)
        raw_response = getattr(response, "raw", None)
        self._debug_log_router(active_thread, conversation, raw_response, parts)
        route = self._parse_conversation_route(parts)
        if route is None:
            self._debug_log_classify(
                latest_user_message,
                f"ROUTER INVALID (parts={parts!r})",
                "ERROR",
            )
            return RouterResult(error="El router LLM devolvió una respuesta inválida.")
        self._debug_log_classify(latest_user_message, f"ROUTER LLM: {parts!r}", route.value)
        return RouterResult(route=route)

    @staticmethod
    def _router_response_parts(response: Any) -> list[str]:
        """Collect every response field where OpenAI-compatible APIs place output.

        DeepSeek-compatible servers may put the decision in ``reasoning_content``
        while ``content`` is empty (or return both). Preserve both fields rather
        than assuming a single OpenAI response shape.
        """
        values: list[Any] = [
            getattr(response, "content", ""),
            getattr(response, "reasoning", ""),
        ]
        raw = getattr(response, "raw", None)
        if isinstance(raw, dict):
            choices = raw.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                message = choices[0].get("message")
                if isinstance(message, dict):
                    values.extend((
                        message.get("content", ""),
                        message.get("reasoning_content", ""),
                        message.get("reasoning", ""),
                    ))
        return [value.strip() for value in values if isinstance(value, str) and value.strip()]

    @staticmethod
    def _parse_conversation_route(raw: str | list[str]) -> ConversationRoute | None:
        """Parse real-world structured or textual router replies, never keywords.

        Structured route objects are preferred.  The textual forms intentionally
        only accept an explicit route label (for example ``Final: MODIFY``), not
        a route word mentioned incidentally in prose or in the prompt.
        """
        candidates = [raw] if isinstance(raw, str) else raw
        route_values = "|".join(route.value for route in ConversationRoute)

        def from_json(value: str) -> ConversationRoute | None:
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(decoded, dict):
                return None
            for key, item in decoded.items():
                if str(key).casefold() == "route":
                    try:
                        return ConversationRoute(str(item).strip().upper())
                    except ValueError:
                        return None
            return None

        for candidate in candidates:
            candidate = candidate.strip()
            route = from_json(candidate)
            if route is not None:
                return route
            # JSON can be wrapped in a markdown fence or embedded after reasoning.
            for json_object in re.findall(r"\{[^{}]*\}", candidate, flags=re.DOTALL):
                route = from_json(json_object)
                if route is not None:
                    return route

        explicit = re.compile(
            rf"(?i)\b(?:ruta(?:\s+seleccionada)?|route|etiqueta|label|final|"
            rf"respuesta(?:\s+final)?|clasificaci[oó]n)\b\s*"
            rf"(?:es|:|=|-)\s*[`*\"']*({route_values})\b",
        )
        bare = re.compile(rf"(?i)^\s*[`*\"']*({route_values})[.!`*\"']*\s*$")
        for candidate in candidates:
            match = explicit.search(candidate)
            if match is None:
                match = bare.match(candidate)
            if match is not None:
                return ConversationRoute(match.group(1).upper())
        return None

    def _debug_log_router(
        self,
        active_thread: str,
        conversation: list[dict[str, str]],
        raw_response: Any,
        parsed_parts: list[str],
    ) -> None:
        """Persist raw router data outside the user project for diagnosis."""
        try:
            debug_dir = RUNS_DIR / f"router-{uuid.uuid4().hex}"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "debug_classify.txt"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "active_thread": active_thread,
                "conversation": conversation,
                "raw_response": raw_response,
                "parsed_parts": parsed_parts,
            }
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(
                    f"[{ts}] ROUTER RAW RESPONSE: "
                    f"{json.dumps(record, ensure_ascii=False, default=str)}\n"
                )
        except Exception:
            pass  # Debug logging must never affect the interaction.

    def classify_intent(self, user_input: str) -> IntentType:
        """Classify the high-level intent of the user input using LLM.

        Returns IntentType.CODE if the user wants code generated,
        IntentType.QUESTION if asking a general question,
        IntentType.CHAT for casual conversation.

        Falls back to heuristic on error/timeout (5s).
        Debug output written to .devflux/debug_classify.txt.
        """
        if self._llm_client is None:
            # No LLM client available — default to CODE
            self._debug_log_classify(user_input, "NO_LLM_CLIENT", "CODE (no client)")
            return IntentType.CODE

        messages = [
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        try:
            t0 = time.time()
            response = self._llm_client.chat(
                messages,
                temperature=0,
                max_tokens=10,
                timeout=5,  # 5s timeout for classification
            )
            elapsed = time.time() - t0
        except Exception as exc:
            # On error/timeout, use heuristic fallback
            fallback = self._heuristic_classify(user_input)
            self._debug_log_classify(
                user_input, f"ERROR: {exc}", f"{fallback.value.upper()} (heuristic fallback)"
            )
            return fallback

        # Parse the response — should be a single word
        raw = response.content.strip().upper() if response.content else ""

        # Accept the word anywhere in the response (in case LLM adds punctuation)
        if "CODE" in raw:
            result = IntentType.CODE
        elif "QUESTION" in raw:
            result = IntentType.QUESTION
        elif "CHAT" in raw:
            result = IntentType.CHAT
        else:
            # Unrecognized response — default to CODE
            result = IntentType.CODE

        self._debug_log_classify(
            user_input,
            f"LLM: {raw} ({elapsed:.2f}s, {response.tokens} tokens)",
            f"{result.value.upper()}"
        )
        return result

    def _debug_log_classify(
        self, user_input: str, detail: str, result: str
    ) -> None:
        """Write classification diagnostics outside the user project."""
        try:
            debug_dir = RUNS_DIR / f"classify-{uuid.uuid4().hex}"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / "debug_classify.txt"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = (
                f"[{ts}] INPUT: {user_input[:120]!r} | "
                f"DETAIL: {detail} | "
                f"RESULT: {result}\n"
            )
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # Debug logging is best-effort; never crash on it

    def _heuristic_classify(self, user_input: str) -> IntentType:
        """Fallback heuristic when LLM classification fails."""
        text = user_input.lower().strip()
        
        # Question patterns (check first)
        question_starts = ("que ", "qué ", "como ", "cómo ", "cual ", "cuál ",
                          "cuando ", "cuándo ", "donde ", "dónde ", "por que ",
                          "por qué ", "quien ", "quién ", "puedes ", "podés ",
                          "podrias ", "podrías ", "sabes ", "tenes ", "tenés ",
                          "me ", "te ", "se ", "explica", "describe", "decime",
                          "contame", "dame", "mostrame", "hay ", "existe ",
                          "conoces ", "conocés ", "viste ", "escuchaste ")
        if any(text.startswith(s) for s in question_starts):
            # But if it also has explicit code keywords, it's CODE
            code_keywords = ("crea ", "crear ", "genera ", "generar ", "haceme ", "hacé ",
                           "construi ", "construí ", "programa ", "desarrolla ",
                           "escribi ", "escribí ", "codifica ", "modifica ",
                           "modificá ", "corregi ", "corregí ", "arregla ",
                           "arreglá ", "fix ", "build ", "create ", "make ")
            if not any(kw in text for kw in code_keywords):
                return IntentType.QUESTION
        
        # Chat patterns
        chat_words = ("hola", "hello", "hi", "buenas", "hey", "gracias", "thanks",
                     "ok", "vale", "bien", "chau", "adios", "bye", "buen", "bueno",
                     "genial", "excelente", "perfecto", "saludos")
        if len(text.split()) <= 3 and any(w in text for w in chat_words):
            return IntentType.CHAT
        
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
