# pylint: disable=redefined-outer-name, unused-argument
"""Fixtures for the unified integration tests."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from requests_mock import Mocker

from custom_components.m365.classes import api
from custom_components.m365.const import MS365_STORAGE_TOKEN
from custom_components.m365.services.calendar import filemgmt_integration as calendar_files
from custom_components.m365.services.todo import filemgmt_integration as todo_files
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from tests.calendar.helpers.utils import build_token_file
from tests.calendar.integration.helpers_integration.mocks import MS365MOCKS as CALENDAR_MOCKS
from tests.contacts.integration.helpers_integration.mocks import MS365MOCKS as CONTACTS_MOCKS
from tests.mail.integration.helpers_integration.mocks import MS365MOCKS as MAIL_MOCKS
from tests.teams.integration.helpers_integration.mocks import MS365MOCKS as TEAMS_MOCKS
from tests.todo.integration.helpers_integration.mocks import MS365MOCKS as TODO_MOCKS

from .const import ALL_TOKEN_PERMS, ENTITY_NAME, UNIFIED_ENTRY_DATA, mail_subentry

STORAGE = "storage"


def _storage_path(tmp_path):
    def _build(hass, filepath):
        if filepath == MS365_STORAGE_TOKEN:
            return tmp_path / STORAGE / "tokens"
        return tmp_path / STORAGE / filepath

    return _build


@pytest.fixture(autouse=True)
def storage_paths(tmp_path):
    """Put tokens and YAML files below tmp_path."""
    (tmp_path / STORAGE / "tokens").mkdir(parents=True, exist_ok=True)
    build = _storage_path(tmp_path)
    with (
        patch.object(api, "build_config_file_path", side_effect=build),
        patch.object(calendar_files, "build_config_file_path", side_effect=build),
        patch.object(todo_files, "build_config_file_path", side_effect=build),
    ):
        yield


@pytest.fixture(autouse=True)
async def request_setup(current_request_with_host: None) -> None:
    """Request setup."""


@pytest.fixture(autouse=True)
def skip_notifications():
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


@pytest.fixture
def all_mocks(requests_mock: Mocker):
    """Mock the Graph calls of every service."""
    for mocks in (CALENDAR_MOCKS, TODO_MOCKS, MAIL_MOCKS, TEAMS_MOCKS, CONTACTS_MOCKS):
        mocks.standard_mocks(requests_mock)
    return requests_mock


@pytest.fixture
def unified_entry(request, hass: HomeAssistant) -> MockConfigEntry:
    """Config entry with all services enabled (overridable via param)."""
    data = deepcopy(UNIFIED_ENTRY_DATA)
    if hasattr(request, "param"):
        data["services"] = request.param
    entry = MockConfigEntry(
        domain="m365",
        title=ENTITY_NAME,
        data=data,
        version=1,
        minor_version=1,
        subentries_data=[mail_subentry()] if "mail" in data["services"] else None,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_unified(hass: HomeAssistant, tmp_path, all_mocks, unified_entry):
    """Set up the unified entry."""
    build_token_file(tmp_path, ALL_TOKEN_PERMS)
    assert await hass.config_entries.async_setup(unified_entry.entry_id)
    await hass.async_block_till_done()
    return unified_entry
