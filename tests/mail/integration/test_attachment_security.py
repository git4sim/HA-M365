# pylint: disable=unused-argument
"""Security tests for mail attachments (added in the unified integration)."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.m365.services.mail import filemgmt_integration, utils_integration
from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError


async def test_notify_rejects_file_outside_allowlist(
    adjust_config_dir,
    hass: HomeAssistant,
    setup_update_integration,
    tmp_path,
) -> None:
    """Files outside allowlist_external_dirs cannot be mailed out."""
    hass.config.allowlist_external_dirs = {str(tmp_path / "www")}
    secret = tmp_path / "secrets.yaml"
    secret.write_text("password: hunter2")

    with (
        patch("O365.connection.Connection.post") as mock_post,
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "m365_test",
            {"message": "Test", "title": "Test", "data": {"attachments": [str(secret)]}},
            blocking=True,
        )
    assert exc_info.value.translation_key == "file_not_allowed"
    assert not mock_post.called


def test_zip_name_cannot_escape(tmp_path) -> None:
    """The archive is always created in a private temporary directory."""
    source = tmp_path / "a.txt"
    source.write_text("a")
    zip_file = utils_integration._zip_files([str(source)], "../../evil")  # noqa: SLF001
    assert Path(zip_file).name == "evil.zip"
    assert Path(zip_file).parent.name.startswith("m365_")
    utils_integration.cleanup([zip_file])
    assert not Path(zip_file).parent.exists()


def test_attachment_name_with_separators(hass: HomeAssistant, tmp_path) -> None:
    """Attachment names from incoming mail cannot leave the attachments folder."""
    (tmp_path / "attachments").mkdir()
    attachment = SimpleNamespace(
        attachment_id="AAMk-123",
        name="../../evil/x.py",
        content=base64.b64encode(b"x").decode(),
    )
    with patch.object(
        filemgmt_integration,
        "build_config_file_path",
        side_effect=lambda hass, path: str(tmp_path / path),
    ):
        filemgmt_integration.save_attachments_to_disk(hass, [SimpleNamespace(attachments=[attachment])])
    assert [p.name for p in (tmp_path / "attachments").iterdir()] == ["123---.._.._evil_x.py"]
