# DevFlux

TUI multi-agente para crear proyectos desde cero. El usuario describe su idea en un chat, y un orquestador encadena equipos de agentes IA que desarrollan el proyecto, lo prueban, y entregan el resultado.

## Instalacion

```bash
pipx install devflux
# o
pip install -e .
```

## Uso

```bash
devflux
```

Al primer inicio, un wizard te guia para configurar el provider (Ollama local o Ollama Cloud).

## Stack

- Python 3.11+
- Textual (TUI)
- httpx (HTTP client)
- Jinja2 (prompt templates)
- PyYAML (config)

## Arquitectura

```
devflux/
├── main.py              # Entrypoint + wizard
├── core/
│   ├── config.py        # DevFluxConfig (dataclass + YAML)
│   ├── credentials.py   # CredentialsStore (API keys, chmod 600)
│   ├── client.py        # LLMClient (httpx, OpenAI-compatible)
│   ├── orchestrator.py  # Orchestrator (classify, Complexity, COMPLEXITY_ROLES)
│   ├── runner.py        # PipelineRunner (roles, retry, extraction, garbage filter, protection)
│   └── sessions.py      # SessionRecord + save/list
├── tui/
│   ├── app.py           # DevFluxApp (TODO el TUI en un archivo)
│   └── styles.tcss      # Estilos
└── prompts/
    └── dev/             # 8 templates Jinja2
```