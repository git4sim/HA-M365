"""Microsoft 365 integration for Home Assistant.

One config entry represents one Microsoft 365 account (one Entra ID app
registration, one token). Calendar, To Do, Mail, Teams and Contacts are
services that can be enabled per account.
"""

import logging

from oauthlib.oauth2.rfc6749.errors import InvalidClientError
from requests.exceptions import HTTPError

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.network import get_url
from homeassistant.helpers.typing import ConfigType

from .classes.api import MS365Account, MS365Token
from .classes.config_entry import MS365ConfigEntry, MS365Data, MS365ServiceData
from .classes.service_entry import MS365ServiceEntry, enabled_services
from .const import (
    CONF_CLIENT_SECRET_VARIABLE,
    CONF_ENTITY_NAME,
    CONF_SHARED_MAILBOX,
    DOMAIN,
    SECRET_EXPIRED,
    TOKEN_ERROR,
    TOKEN_EXPIRED,
    TOKEN_FILE_EXPIRED,
    TOKEN_FILE_MISSING,
)
from .helpers.utils import (
    async_check_personal_account,
    create_issue_id,
    get_credentials,
)
from .permissions import Permissions
from .services import SERVICE_DEFINITIONS, platforms_for

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ISSUE_SERVICE_UNAVAILABLE = "service_unavailable"
# Graph answers that retrying will not change; 401 (auth) and 429
# (throttling) are left to the normal error handling.
SERVICE_REJECTED_STATUS = {400, 403, 404}


def _service_rejection(err: BaseException | None) -> str | None:
    """Return Graph's message if err is a permanent rejection of a service."""
    while err is not None:
        if isinstance(err, HTTPError):
            response = err.response
            if response is not None and response.status_code in SERVICE_REJECTED_STATUS:
                return str(err).split("Error Message: ", 1)[-1]
            return None
        err = err.__cause__
    return None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # pylint: disable=unused-argument
    """Set up the integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MS365ConfigEntry) -> bool:
    """Set up a config entry."""

    _LOGGER.debug("Permissions setup")
    token_backend = MS365Token(hass, entry.data)
    perms = Permissions(hass, entry.data, token_backend)
    ha_account = MS365Account(perms, entry.data)

    with ir.async_refresh_issues(
        hass,
        DOMAIN,
        config_entry_id=entry.entry_id,
    ):
        error = await _async_auth_checks(hass, entry, token_backend, ha_account, perms)

        if error:
            url = f"{get_url(hass)}/config/integrations/integration/{DOMAIN}"
            ir.async_create_issue(
                hass,
                DOMAIN,
                create_issue_id(error, entry.entry_id),
                config_entry_id=entry.entry_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=error,
                translation_placeholders={
                    "domain": DOMAIN,
                    "url": url,
                    CONF_CLIENT_SECRET_VARIABLE: entry.data.get(
                        CONF_CLIENT_SECRET_VARIABLE
                    ),
                    CONF_ENTITY_NAME: entry.data.get(CONF_ENTITY_NAME),
                },
            )
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key=error,
                translation_placeholders={
                    CONF_CLIENT_SECRET_VARIABLE: entry.data.get(
                        CONF_CLIENT_SECRET_VARIABLE
                    ),
                },
            )

    services: dict[str, MS365ServiceData] = {}
    for name in enabled_services(entry.data):
        definition = SERVICE_DEFINITIONS[name]
        _LOGGER.debug("Service setup - %s", name)
        issue_id = create_issue_id(f"{ISSUE_SERVICE_UNAVAILABLE}_{name}", entry.entry_id)
        try:
            coordinator, sensors, platforms = await definition.setup.async_do_setup(
                hass, MS365ServiceEntry(entry, name), ha_account.account
            )
        except (HTTPError, ConfigEntryNotReady) as err:
            # A service rejected by Microsoft (e.g. no Exchange Online mailbox
            # for Calendar/Mail) must not take down the other services.
            if not (message := _service_rejection(err)):
                raise
            _LOGGER.warning(
                "%s - service '%s' is not available for this account and was skipped: %s",
                entry.data.get(CONF_ENTITY_NAME),
                name,
                message,
            )
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                config_entry_id=entry.entry_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_SERVICE_UNAVAILABLE,
                translation_placeholders={
                    "service": name,
                    CONF_ENTITY_NAME: entry.data.get(CONF_ENTITY_NAME),
                    "error": message,
                },
            )
            continue
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        services[name] = MS365ServiceData(coordinator, sensors, list(platforms))

    personal_account = await async_check_personal_account(hass, token_backend)
    entry.runtime_data = MS365Data(
        perms,
        ha_account,
        personal_account,
        services,
        entry.options,
    )
    await hass.config_entries.async_forward_entry_setups(
        entry, platforms_for(services)
    )
    for name in services:
        setup = SERVICE_DEFINITIONS[name].setup
        if hasattr(setup, "async_extra_platform_setup"):
            await setup.async_extra_platform_setup(hass, MS365ServiceEntry(entry, name))

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MS365ConfigEntry) -> bool:
    """Unload a config entry."""
    # Use the services that were set up: a reconfigure may already have
    # changed the enabled services in entry.data before the reload.
    runtime = getattr(entry, "runtime_data", None)
    services = (
        runtime.services
        if isinstance(runtime, MS365Data)
        else enabled_services(entry.data)
    )
    return await hass.config_entries.async_unload_platforms(
        entry, platforms_for(services)
    )


async def async_reload_entry(hass: HomeAssistant, entry: MS365ConfigEntry) -> None:
    """Handle options update - reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: MS365ConfigEntry) -> None:
    """Handle removal of an entry."""
    token_backend = MS365Token(hass, entry.data)
    await hass.async_add_executor_job(token_backend.delete_token)
    for name in enabled_services(entry.data):
        setup = SERVICE_DEFINITIONS[name].setup
        if hasattr(setup, "async_integration_remove_entry"):
            await setup.async_integration_remove_entry(
                hass, MS365ServiceEntry(entry, name)
            )


async def _async_auth_checks(
    hass: HomeAssistant, entry: MS365ConfigEntry, token_backend, ha_account, perms
):
    if not await hass.async_add_executor_job(token_backend.check_token_exists):
        return TOKEN_FILE_MISSING

    credentials, error = get_credentials(entry.data)
    if error:
        return error

    entity_name = entry.data.get(CONF_ENTITY_NAME)
    main_resource = entry.data.get(CONF_SHARED_MAILBOX) or None
    error = (
        await hass.async_add_executor_job(
            ha_account.try_authentication,
            credentials,
            main_resource,
            entity_name,
        )
        or await perms.async_check_authorizations()
    )
    if error:
        return error

    _LOGGER.debug("Do setup")
    token_valid = await _async_check_token_valid(hass, ha_account.account, entity_name)
    return False if token_valid else TOKEN_FILE_EXPIRED


async def _async_check_token_valid(hass: HomeAssistant, account, entity_name):
    try:
        account = await hass.async_add_executor_job(account.get_current_user_data)
        _LOGGER.info("Logged in user: %s, %s", account.full_name, account.object_id)

    except InvalidClientError as err:
        if "client secret" in err.description and "expired" in err.description:
            _LOGGER.warning(SECRET_EXPIRED, entity_name)
        else:
            _LOGGER.warning(TOKEN_ERROR, entity_name, err.description)
        return False
    except RuntimeError as err:
        if "Refresh token operation failed: invalid_grant" in str(err):
            _LOGGER.warning(TOKEN_EXPIRED, entity_name)
            return False
        raise

    return True
