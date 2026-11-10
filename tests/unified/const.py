"""Constants for the unified integration tests."""

ENTITY_NAME = "test"
CLIENT_ID = "1234"

ALL_SERVICES = {
    "calendar": {"enable_update": False, "basic_calendar": False, "groups": False},
    "todo": {"enable_update": False},
    "mail": {"enable_update": False, "enable_autoreply": False},
    "teams": {"chat_enable": "Read", "status_enable": "Read"},
    "contacts": {},
}

UNIFIED_ENTRY_DATA = {
    "entity_name": ENTITY_NAME,
    "client_id": CLIENT_ID,
    "environment_secret": False,
    "client_secret": "5678",
    "alt_auth_method": False,
    "shared_mailbox": "",
    "api_options": {"country": "Default"},
    "services": ALL_SERVICES,
}

ALL_TOKEN_PERMS = "Calendars.Read Tasks.Read Mail.Read Chat.Read Presence.Read Contacts.Read"

ACCOUNT_INPUT = {
    "entity_name": ENTITY_NAME,
    "client_id": CLIENT_ID,
    "environment_secret": False,
    "client_secret": "5678",
    "alt_auth_method": False,
    "api_options": {"country": "Default"},
}


def mail_subentry(name=ENTITY_NAME):
    """Return the default mail subentry."""
    return {
        "data": {"entity_name": name},
        "subentry_type": "mail",
        "title": name,
        "unique_id": f"m365_{name}_{name}",
    }
