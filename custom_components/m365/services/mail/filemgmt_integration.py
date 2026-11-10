"""File management for MS 365 Mail."""

import base64
import os

from homeassistant.core import HomeAssistant

from ...helpers.filemgmt import build_config_file_path
from .const_integration import ATTACHMENT_FOLDER


def check_and_create_attachments_folder(hass: HomeAssistant):
    """Check if attachments folder exists and create if needed."""

    directory = build_config_file_path(hass, ATTACHMENT_FOLDER)
    if not os.path.exists(directory):
        os.makedirs(directory)


def save_attachments_to_disk(hass: HomeAssistant, data):
    """Save attachments."""
    for mail in data:
        for x in mail.attachments:
            attachment_id = x.attachment_id[(x.attachment_id.find("-") + 1) :]
            file_name = build_config_file_path(
                hass,
                os.path.join(
                    ATTACHMENT_FOLDER,
                    _safe_name(f"{attachment_id}---{x.name}"),
                ),
            )
            try:
                with open(file_name, "xb") as file:
                    file.write(base64.b64decode(x.content))
            except FileExistsError:
                pass


def _safe_name(name: str) -> str:
    """Return a file name without path separators.

    Attachment names come from incoming mail. Upstream used them as is, so a
    name containing a path separator made every update fail.
    """
    name = name.replace("\\", "_").replace("/", "_").replace("\0", "_")
    return name.lstrip(".") or "attachment"
