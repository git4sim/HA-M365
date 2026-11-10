# pylint: disable=unused-argument
"""Tests of the unified M365 integration: one account, several services."""

from copy import deepcopy

import pytest
from requests_mock import Mocker

from custom_components.m365.config_flow import MS365ConfigFlow
from custom_components.m365.diagnostics import async_get_config_entry_diagnostics
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry

from tests.calendar.helpers.utils import build_token_file, build_token_url, mock_token
from tests.calendar.integration.const_integration import AUTH_CALLBACK_PATH_DEFAULT

from .const import ACCOUNT_INPUT, ALL_SERVICES, ALL_TOKEN_PERMS, ENTITY_NAME, UNIFIED_ENTRY_DATA

DOMAIN = "m365"

ALL_ENTITIES = [
    "calendar.test_calendar1",
    "todo.test_todo_list_1",
    "sensor.test_mail",
    "sensor.test_status",
    "sensor.test_chat",
]


async def test_all_services_one_account(hass: HomeAssistant, setup_unified) -> None:
    """All services run side by side on a single config entry."""
    entry = setup_unified
    assert entry.state is ConfigEntryState.LOADED
    for entity_id in ALL_ENTITIES:
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.services.has_service(DOMAIN, "contacts_search")
    # Update actions are only registered when updates are enabled
    assert not hass.services.has_service(DOMAIN, "create_calendar_event")
    assert set(entry.runtime_data.services) == set(ALL_SERVICES)


async def test_requested_permissions_are_union(hass: HomeAssistant, setup_unified) -> None:
    """One token covers the permissions of all services."""
    requested = setup_unified.runtime_data.permissions.requested_permissions
    assert requested == [
        "User.Read",
        "Calendars.Read",
        "Tasks.Read",
        "Mail.Read",
        "Chat.Read",
        "Presence.Read",
        "Contacts.Read",
    ]


async def test_diagnostics_per_service(hass: HomeAssistant, setup_unified) -> None:
    """Diagnostics contain the YAML of calendar and todo, keyed by service."""
    result = await async_get_config_entry_diagnostics(hass, setup_unified)
    assert set(result["YAML"]) == {"calendar", "todo"}
    assert result["config_entry_data"]["client_id"] == "**REDACTED**"


@pytest.mark.parametrize("unified_entry", [{"calendar": ALL_SERVICES["calendar"]}], indirect=True)
async def test_only_enabled_services(hass: HomeAssistant, setup_unified) -> None:
    """Disabled services create no entities, actions or permissions."""
    assert hass.states.get("calendar.test_calendar1") is not None
    assert hass.states.get("todo.test_todo_list_1") is None
    assert hass.states.get("sensor.test_status") is None
    assert not hass.services.has_service(DOMAIN, "contacts_search")
    assert setup_unified.runtime_data.permissions.requested_permissions == [
        "User.Read",
        "Calendars.Read",
    ]
    assert MS365ConfigFlow.async_get_supported_subentry_types(setup_unified) == {}


async def test_unload(hass: HomeAssistant, setup_unified) -> None:
    """The entry unloads all its platforms."""
    assert await hass.config_entries.async_unload(setup_unified.entry_id)
    assert setup_unified.state is ConfigEntryState.NOT_LOADED


async def test_mail_subentry_type_offered(hass: HomeAssistant, setup_unified) -> None:
    """Mail folders are subentries when Mail is enabled."""
    assert set(MS365ConfigFlow.async_get_supported_subentry_types(setup_unified)) == {"mail"}


async def test_options_menu(hass: HomeAssistant, setup_unified) -> None:
    """The options flow offers the services with options and stores per service."""
    result = await hass.config_entries.options.async_init(setup_unified.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["calendar", "todo", "teams"]

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "teams"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "teams_user"

    result = await hass.config_entries.options.async_configure(result["flow_id"], {"update_interval": 5})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert setup_unified.options == {"teams": {"update_interval": 5}}
    assert setup_unified.state is ConfigEntryState.LOADED

    result = await hass.config_entries.options.async_init(setup_unified.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "todo"})
    assert result["step_id"] == "todo_user"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"track_new": False, "max_todos": 50, "todo_list": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert setup_unified.options["teams"] == {"update_interval": 5}
    assert setup_unified.options["todo"]["max_todos"] == 50


async def test_config_flow_multiple_services(hass: HomeAssistant, requests_mock: Mocker, all_mocks) -> None:
    """Set up calendar and teams on one account in a single flow."""
    mock_token(requests_mock, "Calendars.ReadWrite Chat.Read Presence.Read")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**ACCOUNT_INPUT, "services": []})
    assert result["errors"] == {"services": "no_services"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ACCOUNT_INPUT, "services": ["calendar", "teams"]}
    )
    assert result["step_id"] == "services"
    assert set(result["data_schema"].schema) == {"calendar", "teams"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "calendar": {"enable_update": True, "basic_calendar": False, "groups": False},
            "teams": {"chat_enable": "Read", "status_enable": "Read"},
        },
    )
    assert result["step_id"] == "request_default"
    assert "Calendars.ReadWrite" in result["description_placeholders"]["auth_url"]
    assert "Chat.Read" in result["description_placeholders"]["auth_url"]
    assert "Mail" not in result["description_placeholders"]["auth_url"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["entity_name"] == ENTITY_NAME
    assert data["services"] == {
        "calendar": {"enable_update": True, "basic_calendar": False, "groups": False},
        "teams": {"chat_enable": "Read", "status_enable": "Read"},
    }
    assert not result["result"].subentries


async def test_config_flow_service_validation(hass: HomeAssistant, requests_mock: Mocker, all_mocks) -> None:
    """Service settings are validated per service section."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ACCOUNT_INPUT, "services": ["teams"]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"teams": {"chat_enable": "Read", "status_enable": "Update", "alternate_email": "a@b.c"}},
    )
    assert result["step_id"] == "services"
    assert result["errors"] == {"teams": "status_enable_should_be_read"}


async def test_config_flow_contacts_only_skips_services_step(
    hass: HomeAssistant, requests_mock: Mocker, all_mocks
) -> None:
    """Contacts has no settings, so the services step is skipped."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ACCOUNT_INPUT, "services": ["contacts"]}
    )
    assert result["step_id"] == "request_default"


async def test_config_flow_mail_creates_subentry(hass: HomeAssistant, requests_mock: Mocker, all_mocks) -> None:
    """Enabling Mail creates the default inbox subentry."""
    mock_token(requests_mock, "Mail.Read")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**ACCOUNT_INPUT, "services": ["mail"]})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mail": {"enable_update": False, "enable_autoreply": False}}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentries = list(result["result"].subentries.values())
    assert [subentry.subentry_type for subentry in subentries] == ["mail"]


async def test_reconfigure_remove_service(
    hass: HomeAssistant, requests_mock: Mocker, tmp_path, setup_unified
) -> None:
    """Removing a service removes its entities and options; others stay."""
    entry = setup_unified
    registry = er.async_get(hass)
    hass.config_entries.async_update_entry(entry, options={"teams": {"update_interval": 5}, "todo": {"max_todos": 50}})
    await hass.async_block_till_done()
    assert registry.async_get("sensor.test_status") is not None

    mock_token(requests_mock, "Calendars.Read Tasks.Read Mail.Read Contacts.Read")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    account = {key: value for key, value in ACCOUNT_INPUT.items() if key != "entity_name"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**account, "services": ["calendar", "todo", "mail", "contacts"]}
    )
    assert result["step_id"] == "services"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {key: value for key, value in ALL_SERVICES.items() if key in ("calendar", "todo", "mail")},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert set(entry.data["services"]) == {"calendar", "todo", "mail", "contacts"}
    assert entry.options == {"todo": {"max_todos": 50}}
    assert registry.async_get("sensor.test_status") is None
    assert registry.async_get("sensor.test_chat") is None
    assert registry.async_get("sensor.test_mail") is not None
    assert registry.async_get("calendar.test_calendar1") is not None
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.parametrize("unified_entry", [{"calendar": ALL_SERVICES["calendar"]}], indirect=True)
async def test_reconfigure_add_mail(hass: HomeAssistant, requests_mock: Mocker, setup_unified) -> None:
    """Adding Mail later creates its default subentry."""
    entry = setup_unified
    mock_token(requests_mock, "Calendars.Read Mail.Read")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    account = {key: value for key, value in ACCOUNT_INPUT.items() if key != "entity_name"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**account, "services": ["calendar", "mail"]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"calendar": ALL_SERVICES["calendar"], "mail": ALL_SERVICES["mail"]},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert [sub.subentry_type for sub in entry.subentries.values()] == ["mail"]
    assert hass.states.get("sensor.test_mail") is not None


async def test_contacts_search_multiple_accounts(hass: HomeAssistant, tmp_path, all_mocks, setup_unified) -> None:
    """With two accounts, contacts_search needs the account to search."""
    second_data = deepcopy(UNIFIED_ENTRY_DATA)
    second_data["entity_name"] = "test2"
    second_data["services"] = {"contacts": {}}
    tokens = tmp_path / "storage" / "tokens"
    (tokens / "m365_test2.token").write_text((tokens / "m365_test.token").read_text())
    second = MockConfigEntry(domain=DOMAIN, title="test2", data=second_data, version=1, minor_version=1)
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "contacts_search", {"given_name": "Roger"}, blocking=True, return_response=True
        )

    response = await hass.services.async_call(
        DOMAIN,
        "contacts_search",
        {"given_name": "Roger", "config_entry_id": second.entry_id},
        blocking=True,
        return_response=True,
    )
    assert response["contacts"]

    assert await hass.config_entries.async_unload(second.entry_id)
    response = await hass.services.async_call(
        DOMAIN, "contacts_search", {"given_name": "Roger"}, blocking=True, return_response=True
    )
    assert response["contacts"]


async def test_token_shared_by_services(hass: HomeAssistant, tmp_path, setup_unified) -> None:
    """There is exactly one token file for the account."""
    tokens = sorted(p.name for p in (tmp_path / "storage" / "tokens").iterdir())
    assert tokens == ["m365_test.token"]
    build_token_file(tmp_path, ALL_TOKEN_PERMS)


async def test_reauth_flow(hass: HomeAssistant, requests_mock: Mocker, setup_unified) -> None:
    """The reauth flow started by Home Assistant re-authenticates the account."""
    entry = setup_unified
    mock_token(requests_mock, ALL_TOKEN_PERMS)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "user"
    account = {key: value for key, value in ACCOUNT_INPUT.items() if key != "entity_name"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**account, "services": list(ALL_SERVICES)}
    )
    assert result["step_id"] == "services"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {key: value for key, value in ALL_SERVICES.items() if value}
    )
    assert result["step_id"] == "request_default"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


MAILBOX_ERROR = {
    "error": {
        "code": "MailboxNotEnabledForRESTAPI",
        "message": "The mailbox is either inactive, soft-deleted, or is hosted on-premise.",
    }
}


async def test_rejected_service_is_skipped(
    hass: HomeAssistant, tmp_path, all_mocks: Mocker, unified_entry
) -> None:
    """A service Microsoft rejects (no mailbox) does not break the others."""
    all_mocks.get(
        "https://graph.microsoft.com/v1.0/me/calendars", status_code=404, json=MAILBOX_ERROR
    )
    all_mocks.get(
        "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages", status_code=404, json=MAILBOX_ERROR
    )
    build_token_file(tmp_path, ALL_TOKEN_PERMS)
    assert await hass.config_entries.async_setup(unified_entry.entry_id)
    await hass.async_block_till_done()

    assert unified_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("calendar.test_calendar1") is None
    assert hass.states.get("todo.test_todo_list_1") is not None
    assert hass.states.get("sensor.test_status") is not None
    assert "calendar" not in unified_entry.runtime_data.services

    issues = ir.async_get(hass).issues
    issue = issues[(DOMAIN, f"service_unavailable_calendar_{unified_entry.entry_id}")]
    assert issue.translation_placeholders["error"].startswith("The mailbox is either inactive")
    assert await hass.config_entries.async_unload(unified_entry.entry_id)


async def test_transient_error_is_not_skipped(
    hass: HomeAssistant, tmp_path, all_mocks: Mocker, unified_entry
) -> None:
    """Server errors still make the whole entry retry."""
    all_mocks.get("https://graph.microsoft.com/v1.0/me/calendars", status_code=503, json={"error": {}})
    build_token_file(tmp_path, ALL_TOKEN_PERMS)
    await hass.config_entries.async_setup(unified_entry.entry_id)
    await hass.async_block_till_done()
    assert unified_entry.state is not ConfigEntryState.LOADED
