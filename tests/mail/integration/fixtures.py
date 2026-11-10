# pylint: disable=redefined-outer-name, unused-argument
"""Fixtures specific to the integration."""

from copy import deepcopy

import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def adjust_config_dir(
    tmp_path,
    hass: HomeAssistant,
):  # pylint: disable=unused-argument
    """Fake the HASS config directory."""
    old_path = deepcopy(hass.config.config_dir)
    old_allowlist = set(hass.config.allowlist_external_dirs)
    hass.config.config_dir = deepcopy(tmp_path)
    # Attachments must be in an allowed directory (see utils_integration)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    yield
    hass.config.config_dir = old_path
    hass.config.allowlist_external_dirs = old_allowlist
