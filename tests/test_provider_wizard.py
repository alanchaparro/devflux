from __future__ import annotations

import pytest

from devflux.core.config import DevFluxConfig, normalize_provider
from devflux.tui.app import DevFluxApp, MenuWidget


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ollama-cloud", "ollama-cloud"),
        ("ollama–cloud", "ollama-cloud"),
        ("OLLAMA-CLOUD", "ollama-cloud"),
        ("  ollama - cloud  ", "ollama-cloud"),
        ("ollama‑local", "ollama-local"),
    ],
)
def test_normalize_provider_returns_canonical_supported_provider(raw: str, expected: str) -> None:
    assert normalize_provider(raw) == expected


def test_normalize_provider_rejects_unknown_provider() -> None:
    assert normalize_provider("other-provider") is None


def test_load_normalizes_existing_provider_and_persists_canonical_value(tmp_path, monkeypatch) -> None:
    import devflux.core.config as config_module

    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(config_module, "DEVFLUX_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    config_path.write_text("provider: OLLAMA–CLOUD\nmodel: qwen3-coder\n", encoding="utf-8")

    config = DevFluxConfig.load()

    assert config is not None
    assert config.provider == "ollama-cloud"
    assert "provider: ollama-cloud" in config_path.read_text(encoding="utf-8")


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    import devflux.core.config as config_module
    import devflux.core.credentials as credentials_module

    monkeypatch.setattr(config_module, "DEVFLUX_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(credentials_module, "DEVFLUX_DIR", tmp_path)
    monkeypatch.setattr(credentials_module, "CREDS_PATH", tmp_path / "credentials.yaml")
    return tmp_path


@pytest.mark.asyncio
async def test_first_setup_shows_provider_selector_not_provider_text_input(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test():
        selector = app.query_one("#wizard-selector", MenuWidget)
        assert selector.visible
        assert selector._items == ["Ollama Cloud", "Ollama Local"]
        assert not app.query_one("#wizard-input").visible
        assert "ollama-cloud" not in str(app.query_one("#wizard-content").render())


@pytest.mark.asyncio
async def test_down_enter_selects_local_then_model_without_api_key(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test() as pilot:
        await pilot.press("down", "enter")
        assert app._pending_provider == "ollama-local"
        assert app._wizard_step == "model"
        assert not app.query_one("#wizard-input").visible
        assert app.query_one("#wizard-selector", MenuWidget)._items[0] == "llama3.2"

        await pilot.press("enter")
        await pilot.pause()
        assert app._config is not None
        assert app._config.provider == "ollama-local"
        assert app.query("#chat-input")

    saved = DevFluxConfig.load()
    assert saved is not None
    assert saved.provider == "ollama-local"


@pytest.mark.asyncio
async def test_cloud_only_asks_for_key_then_keyboard_model_selector(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test() as pilot:
        await pilot.press("enter")
        assert app._wizard_step == "api_key"
        assert app.query_one("#wizard-input").visible
        assert app._pending_provider == "ollama-cloud"

        app.query_one("#wizard-input").value = "x"
        await pilot.press("enter")
        assert app._wizard_step == "model"
        assert not app.query_one("#wizard-input").visible
        assert app.query_one("#wizard-selector", MenuWidget)._items[0] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_settings_provider_selector_is_preselected_and_persists_canonical_value(isolated_config) -> None:
    DevFluxConfig(provider="ollama-local").save()
    app = DevFluxApp()

    async with app.run_test() as pilot:
        app._change_provider()
        selector = app.query_one("#menu-widget", MenuWidget)
        assert selector.visible
        assert selector._items == ["Ollama Cloud", "Ollama Local"]
        assert selector._selected == 1

        await pilot.press("up", "enter")
        assert app._settings_input_mode == "model_selector"
        assert selector._items[0] == "deepseek-v4-pro"
        await pilot.press("enter")
        assert app._config is not None
        assert app._config.provider == "ollama-cloud"

    assert DevFluxConfig.load().provider == "ollama-cloud"


@pytest.mark.asyncio
async def test_valid_saved_config_skips_wizard_after_restart(isolated_config) -> None:
    DevFluxConfig(provider="ollama–local").save()
    app = DevFluxApp()

    async with app.run_test():
        assert app._config is not None
        assert app._config.provider == "ollama-local"
        assert not app.query("#wizard-selector")
        assert app.query("#chat-input")
