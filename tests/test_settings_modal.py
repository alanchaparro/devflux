from __future__ import annotations

import pytest
from textual.widgets import Button, Input, OptionList

from devflux.core.config import DevFluxConfig, PROVIDERS
from devflux.tui.app import DevFluxApp, SettingsScreen


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    import devflux.core.config as config_module
    import devflux.core.credentials as credentials_module

    monkeypatch.setattr(config_module, "DEVFLUX_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(credentials_module, "DEVFLUX_DIR", tmp_path)
    monkeypatch.setattr(credentials_module, "CREDS_PATH", tmp_path / "credentials.yaml")
    DevFluxConfig(provider="ollama-local", model="llama3.2").save()
    return tmp_path


async def open_settings_from_menu(app: DevFluxApp, pilot) -> SettingsScreen:
    await pilot.press("ctrl+s", "down", "down", "enter")
    assert isinstance(app.screen, SettingsScreen)
    return app.screen


@pytest.mark.asyncio
async def test_settings_menu_opens_a_fullscreen_modal_screen(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_settings_from_menu(app, pilot)

        assert screen.size == app.size
        assert screen.query_one("#settings-provider", OptionList).option_count == 2
        assert screen.query_one("#settings-model", OptionList).option_count == len(
            PROVIDERS["ollama-local"]["models"]
        )
        assert screen.query_one("#settings-save", Button).visible
        assert screen.query_one("#settings-cancel", Button).visible


@pytest.mark.asyncio
async def test_settings_cancel_discards_provider_and_model_changes(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test() as pilot:
        screen = await open_settings_from_menu(app, pilot)
        await pilot.press("down", "enter")
        assert screen.draft_provider == "ollama-cloud"

        await pilot.press("escape")
        assert not isinstance(app.screen, SettingsScreen)
        assert app._config is not None
        assert app._config.provider == "ollama-local"
        assert DevFluxConfig.load() is not None
        assert DevFluxConfig.load().provider == "ollama-local"


@pytest.mark.asyncio
async def test_settings_save_persists_selected_provider_model_and_secret_key(isolated_config) -> None:
    app = DevFluxApp()

    async with app.run_test() as pilot:
        screen = await open_settings_from_menu(app, pilot)
        await pilot.press("down", "enter")
        assert screen.draft_provider == "ollama-cloud"

        key_input = screen.query_one("#settings-api-key", Input)
        assert key_input.visible
        assert key_input.password
        assert key_input.value == ""
        key_input.value = "new-secret"

        model_list = screen.query_one("#settings-model", OptionList)
        model_list.focus()
        await pilot.press("down", "enter")
        selected_model = screen.draft_model

        screen.query_one("#settings-save", Button).focus()
        await pilot.press("enter")

        assert not isinstance(app.screen, SettingsScreen)
        assert app._config is not None
        assert app._config.provider == "ollama-cloud"
        assert app._config.model == selected_model
        assert app._creds.get("ollama-cloud") == "new-secret"
        assert DevFluxConfig.load() is not None
        assert DevFluxConfig.load().provider == "ollama-cloud"


@pytest.mark.asyncio
async def test_settings_model_load_failure_is_human_and_offers_retry_or_return(isolated_config, monkeypatch) -> None:
    app = DevFluxApp()

    async with app.run_test() as pilot:
        monkeypatch.setitem(PROVIDERS["ollama-local"], "models", [])
        app._open_settings()
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        screen = app.screen
        message = str(screen.query_one("#settings-model-error").render())

        assert "No pudimos cargar los modelos" in message
        assert screen.query_one("#settings-retry", Button).visible
        assert screen.query_one("#settings-back", Button).visible
        assert "Traceback" not in message

        await pilot.press("escape")
        assert not isinstance(app.screen, SettingsScreen)


@pytest.mark.asyncio
async def test_settings_model_list_navigates_large_catalog_without_dynamic_ids(isolated_config, monkeypatch) -> None:
    models = [f"model-{index:03d}-with-a-long-name" for index in range(90)]
    monkeypatch.setitem(PROVIDERS["ollama-local"], "models", models)
    app = DevFluxApp()

    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_settings_from_menu(app, pilot)
        model_list = screen.query_one("#settings-model", OptionList)

        assert model_list.option_count == len(models)
        model_list.focus()
        await pilot.press("end", "enter")
        assert screen.draft_model == models[-1]
        assert model_list.highlighted == len(models) - 1

        await pilot.press("escape")
