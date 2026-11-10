"""Configuration flow for the unified M365 integration.

Steps:
    user        account credentials, services to enable, shared mailbox
    services    per-service settings, one collapsible section per service
    request_*   authorisation against Microsoft (default or alternate method)
"""

from collections.abc import Mapping
from copy import deepcopy
import functools as ft
import logging
from typing import Any, Self
from urllib.parse import parse_qs, urlparse

from aiohttp import web_response
import probatio

from homeassistant import data_entry_flow
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    SOURCE_REAUTH,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.network import get_url
from homeassistant.helpers.selector import BooleanSelector

from .classes.api import MS365Account, MS365Token
from .classes.config_entry import MS365ConfigEntry
from .classes.service_entry import (
    MS365ServiceEntry,
    build_service_data,
    enabled_services,
)
from .const import (
    AUTH_CALLBACK_DATA,
    AUTH_CALLBACK_NAME,
    AUTH_CALLBACK_PATH_ALT,
    AUTH_ERROR_ALREADY_CONFIGURED,
    AUTH_ERROR_AUTHENTICATING,
    AUTH_ERROR_INVALID_TENANT,
    CONF_ALT_AUTH_METHOD,
    CONF_API_COUNTRY,
    CONF_API_OPTIONS,
    CONF_AUTH_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CLIENT_SECRET_VARIABLE,
    CONF_ENTITY_NAME,
    CONF_ENVIRONMENT_SECRET,
    CONF_FAILED_PERMISSIONS,
    CONF_SERVICES,
    CONF_SHARED_MAILBOX,
    CONF_TENANT_ID,
    CONF_URL,
    COUNTRY_URLS,
    DEFAULT_TENANT_ID,
    DOMAIN,
    ERROR_INVALID_SHARED_MAILBOX,
    ERROR_INVALID_TENANT,
    ERROR_INVALID_URL,
    MS365_CLIENT_SECRET,
    OAUTH_REDIRECT_URL,
    SERVICE_CALENDAR,
    SERVICE_MAIL,
    SERVICE_TEAMS,
    SERVICE_TODO,
    TOKEN_ERROR_FILE,
    TOKEN_FILE_CORRUPTED,
    TOKEN_FILE_OUTDATED,
    CountryOptions,
)
from .helpers.utils import get_country, get_credentials, get_tenant_id
from .permissions import Permissions
from .schema import CONFIG_SCHEMA, REQUEST_AUTHORIZATION_DEFAULT_SCHEMA, SERVICES_SELECTOR
from .services import SERVICE_DEFINITIONS
from .services.mail.config_flow_integration import MailSubentryFlow, subentry_setup
from .services.mail.const_integration import SUBENTRY_MAIL

_LOGGER = logging.getLogger(__name__)

CONFIG_VERSION = 1
CONFIG_MINOR_VERSION = 1

ERROR_NO_SERVICES = "no_services"


class MS365ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for a Microsoft 365 account."""

    VERSION = CONFIG_VERSION
    MINOR_VERSION = CONFIG_MINOR_VERSION

    def __init__(self) -> None:
        """Initialise the configuration flow."""
        self._permissions = []
        self._ms365account = None
        self.entity_name = None
        self._url = None
        self._flow = None
        self._callback_urls = None
        self._user_input: dict[str, Any] = {}
        self._selected_services: list[str] = []
        self._config_schema: dict | None = None
        self._reconfigure = False
        self._entry: MS365ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """M365 options callback."""
        return MS365OptionsFlowHandler(config_entry)

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the subentry types (mail folders, if Mail is enabled)."""
        if SERVICE_MAIL in enabled_services(config_entry.data):
            return {SUBENTRY_MAIL: MailSubentryFlow}
        return {}

    def is_matching(self, other_flow: Self) -> bool:  # pragma: no cover
        """Return True if other_flow is matching this flow."""
        return other_flow.entity_name == self.entity_name

    # ------------------------------------------------------------------ steps

    async def async_step_user(self, user_input=None):
        """Handle the account step."""
        errors = {}
        if user_input:
            user_input = dict(user_input)
            selected = [
                name
                for name in user_input.pop(CONF_SERVICES, [])
                if name in SERVICE_DEFINITIONS
            ]
            if self._reconfigure:
                user_input[CONF_ENTITY_NAME] = self.entity_name
            elif self._check_existing(user_input.get(CONF_ENTITY_NAME)):
                errors[CONF_ENTITY_NAME] = AUTH_ERROR_ALREADY_CONFIGURED
            if not selected:
                errors[CONF_SERVICES] = ERROR_NO_SERVICES
            if not errors:
                if not self._reconfigure:
                    self.entity_name = user_input[CONF_ENTITY_NAME]
                self._selected_services = selected
                self._user_input = user_input
                return await self.async_step_services()

        data = self._config_schema or CONFIG_SCHEMA
        return self.async_show_form(
            step_id="user", data_schema=probatio.Schema(data), errors=errors
        )

    async def async_step_services(self, user_input=None):
        """Handle the per-service settings."""
        schema = self._services_schema()
        errors = {}
        if user_input is not None or not schema:
            user_input = user_input or {}
            services = {
                name: dict(user_input.get(name) or {})
                for name in self._selected_services
            }
            data = {**self._user_input, CONF_SERVICES: services}
            for name in self._selected_services:
                if error := SERVICE_DEFINITIONS[name].validate(
                    build_service_data(data, name)
                ):
                    errors[name] = next(iter(error.values()))
            if not errors:
                self._user_input = data
                alt_auth_method = data.get(CONF_ALT_AUTH_METHOD)
                errors = await self._validate_user_input_for_auth(data, alt_auth_method)
                if not errors:
                    if alt_auth_method:
                        return await self.async_step_request_alt()
                    return await self.async_step_request_default()
                # Authentication errors relate to the account settings.
                return self.async_show_form(
                    step_id="user",
                    data_schema=probatio.Schema(self._config_schema or CONFIG_SCHEMA),
                    errors=errors,
                )

        return self.async_show_form(
            step_id="services",
            data_schema=probatio.Schema(schema),
            description_placeholders={CONF_ENTITY_NAME: self.entity_name},
            errors=errors,
        )

    def _services_schema(self) -> dict:
        previous = self._entry.data if self._reconfigure and self._entry else {}
        previously_enabled = enabled_services(previous)
        schema = {}
        for name in self._selected_services:
            definition = SERVICE_DEFINITIONS[name]
            if name in previously_enabled:
                fields = definition.reconfigure_schema(
                    build_service_data(previous, name)
                )
            else:
                fields = definition.config_schema()
            if fields:
                schema[probatio.Required(name)] = section(
                    probatio.Schema(fields), {"collapsed": False}
                )
        return schema

    async def _validate_user_input_for_auth(self, user_input, alt_auth_method):
        credentials, error = get_credentials(user_input)
        if error:
            return {CONF_ENVIRONMENT_SECRET: error}

        main_resource = user_input.get(CONF_SHARED_MAILBOX) or None
        token_backend = MS365Token(self.hass, user_input)
        self._permissions = Permissions(self.hass, user_input, token_backend)
        self._ms365account = MS365Account(self._permissions, user_input)
        auth_error = await self.hass.async_add_executor_job(
            self._ms365account.try_authentication,
            credentials,
            main_resource,
            self.entity_name,
        )
        auth_error = await self._async_delete_unreadable_token(
            auth_error, token_backend
        ) or await self._async_get_authorization_url(alt_auth_method, user_input)

        if auth_error == AUTH_ERROR_INVALID_TENANT:
            return {CONF_API_OPTIONS: auth_error}

        if auth_error:
            attr_name = CONF_CLIENT_ID if self._reconfigure else CONF_ENTITY_NAME
            return {attr_name: AUTH_ERROR_AUTHENTICATING}

        return {}

    async def _async_get_authorization_url(self, alt_auth_method, user_input):
        scope = self._permissions.requested_permissions
        try:
            self._url, self._flow = await self.hass.async_add_executor_job(
                ft.partial(
                    self._ms365account.account.get_authorization_url,
                    requested_scopes=scope,
                    redirect_uri=get_callback_url(
                        self.hass, alt_auth_method, user_input
                    ),
                )
            )
        except ValueError as err:
            _LOGGER.warning(ERROR_INVALID_TENANT, err)
            return AUTH_ERROR_INVALID_TENANT
        return False

    async def async_step_request_default(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to paste the returned url."""
        errors = {}
        if user_input is not None:
            errors = await self._async_validate_response(user_input)
            if not errors:
                return await self._async_create_update_entry()

        return self.async_show_form(
            step_id="request_default",
            data_schema=probatio.Schema(REQUEST_AUTHORIZATION_DEFAULT_SCHEMA),
            description_placeholders={
                CONF_AUTH_URL: self._url,
                CONF_ENTITY_NAME: self.entity_name,
                CONF_FAILED_PERMISSIONS: self._failed_perms(),
            },
            errors=errors,
        )

    async def async_step_request_alt(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Wait for the callback of the alternate method."""
        errors = {}
        if user_input is not None:
            errors = await self._async_validate_response(user_input)
            if not errors:
                return await self._async_create_update_entry()

        if self._callback_urls is None:
            self._callback_urls = _async_get_callback_urls(self.hass)
            self._callback_urls[self._flow["state"]] = ""

        return self.async_show_form(
            step_id="request_alt",
            description_placeholders={
                CONF_AUTH_URL: self._url,
                CONF_ENTITY_NAME: self.entity_name,
                CONF_FAILED_PERMISSIONS: self._failed_perms(),
            },
            errors=errors,
        )

    def _failed_perms(self):
        return (
            f"\n\nMissing - {', '.join(self._permissions.failed_permissions)}"
            if self._permissions.failed_permissions
            else None
        )

    async def _async_create_update_entry(self):
        if self._reconfigure:
            removed = [
                name
                for name in enabled_services(self._entry.data)
                if name not in enabled_services(self._user_input)
            ]
            added = [
                name
                for name in enabled_services(self._user_input)
                if name not in enabled_services(self._entry.data)
            ]
            await self._async_cleanup_removed_services(removed)
            if SERVICE_MAIL in added and not self._entry.get_subentries_of_type(
                SUBENTRY_MAIL
            ):
                for subentry in subentry_setup(self.entity_name):
                    self.hass.config_entries.async_add_subentry(
                        self._entry, ConfigSubentry(**subentry)
                    )
            options = {
                key: value
                for key, value in self._entry.options.items()
                if key not in removed
            }
            # The update listener of a loaded entry reloads it when it changes
            loaded = self._entry.state is ConfigEntryState.LOADED
            changed = self.hass.config_entries.async_update_entry(
                self._entry, data=self._user_input, options=options
            )
            if not (loaded and changed):
                self.hass.config_entries.async_schedule_reload(self._entry.entry_id)
            return self.async_abort(
                reason="reauth_successful"
                if self.source == SOURCE_REAUTH
                else "reconfigure_successful"
            )

        subentries = None
        if SERVICE_MAIL in enabled_services(self._user_input):
            subentries = subentry_setup(self._user_input[CONF_ENTITY_NAME])
        return self.async_create_entry(
            title=self.entity_name, data=self._user_input, subentries=subentries
        )

    async def _async_cleanup_removed_services(self, removed: list[str]) -> None:
        """Remove entities, subentries and files of services that were disabled."""
        if not removed:
            return
        entry = self._entry
        registry = er.async_get(self.hass)
        removed_domains = {
            Platform.CALENDAR: SERVICE_CALENDAR in removed,
            Platform.TODO: SERVICE_TODO in removed,
        }
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            remove = removed_domains.get(entity.domain, False)
            if entity.domain == Platform.SENSOR:
                is_teams = entity.unique_id.endswith("_ms365")
                remove = (is_teams and SERVICE_TEAMS in removed) or (
                    not is_teams and SERVICE_MAIL in removed
                )
            if remove:
                registry.async_remove(entity.entity_id)
        if SERVICE_MAIL in removed:
            for subentry_id in list(entry.subentries):
                if entry.subentries[subentry_id].subentry_type == SUBENTRY_MAIL:
                    self.hass.config_entries.async_remove_subentry(entry, subentry_id)
        for name in removed:
            setup = SERVICE_DEFINITIONS[name].setup
            if hasattr(setup, "async_integration_remove_entry"):
                await setup.async_integration_remove_entry(
                    self.hass, MS365ServiceEntry(entry, name)
                )

    async def _async_validate_response(self, user_input):
        errors = {}
        alt_auth_method = self._user_input.get(CONF_ALT_AUTH_METHOD)
        error_key = "base" if alt_auth_method else CONF_URL
        url = (
            self._callback_urls.get(self._flow["state"], "")
            if alt_auth_method
            else user_input[CONF_URL]
        )
        if url[:5].lower() == "http:":
            url = f"https:{url[5:]}"
        query = parse_qs(urlparse(url).query)
        if "code" not in query and "error" not in query:
            errors[error_key] = "invalid_url"
            return errors

        if self._ms365account.account.username:
            await self.hass.async_add_executor_job(
                ft.partial(
                    self._ms365account.account.con.token_backend.remove_data,
                    username=self._ms365account.account.username,
                )
            )
        credentials, __ = get_credentials(self._user_input)

        main_resource = self._user_input.get(CONF_SHARED_MAILBOX) or None

        try:
            result = await self.hass.async_add_executor_job(
                ft.partial(
                    self._ms365account.account.request_token,
                    url,
                    flow=self._flow,
                    redirect_uri=get_callback_url(
                        self.hass, alt_auth_method, self._user_input
                    ),
                )
            )
        except ValueError as err:
            _LOGGER.warning(ERROR_INVALID_URL, err)
            errors[error_key] = "invalid_url"
            return errors

        if result is not True:
            _LOGGER.error(TOKEN_ERROR_FILE)
            errors[error_key] = "token_file_error"
            return errors

        __ = await self.hass.async_add_executor_job(
            self._ms365account.try_authentication,
            credentials,
            main_resource,
            self.entity_name,
        )
        if (
            main_resource
            and self._ms365account.account.username
            == self._ms365account.account.main_resource
        ):
            self._user_input[CONF_SHARED_MAILBOX] = ""
            _LOGGER.warning(
                ERROR_INVALID_SHARED_MAILBOX, self._ms365account.account.username
            )

        error = await self._permissions.async_check_authorizations()
        if error:
            errors[error_key] = error

        return errors

    async def async_step_reconfigure(
        self,
        user_input: Mapping[str, Any] | None = None,  # pylint: disable=unused-argument
    ) -> ConfigFlowResult:
        """Trigger a reconfiguration flow."""
        self._entry = self._get_reconfigure_entry()
        assert self._entry
        return await self._redo_configuration(self._entry.data)

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # pylint: disable=unused-argument
    ) -> ConfigFlowResult:
        """Re-authenticate (started by Home Assistant on ConfigEntryAuthFailed).

        Upstream raised ConfigEntryAuthFailed without a reauth step, so the
        "Reauthenticate" button failed; reuse the reconfigure flow instead.
        """
        self._entry = self._get_reauth_entry()
        return await self._redo_configuration(self._entry.data)

    async def _redo_configuration(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Re-run configuration step."""

        self._reconfigure = True
        self.entity_name = entry_data[CONF_ENTITY_NAME]
        country = get_country(entry_data)
        tenant_id = get_tenant_id(entry_data)

        self._config_schema = {
            probatio.Required(
                CONF_CLIENT_ID, default=entry_data[CONF_CLIENT_ID]
            ): probatio.All(cv.string, probatio.Strip),
            probatio.Required(
                CONF_ENVIRONMENT_SECRET,
                default=entry_data.get(CONF_ENVIRONMENT_SECRET, False),
            ): BooleanSelector(),
            data_entry_flow.Required(
                CONF_CLIENT_SECRET,
                default=entry_data.get(CONF_CLIENT_SECRET),
                visible={"field": CONF_ENVIRONMENT_SECRET, "value": False},
            ): probatio.All(cv.string, probatio.Strip),
            data_entry_flow.Required(
                CONF_CLIENT_SECRET_VARIABLE,
                default=entry_data.get(
                    CONF_CLIENT_SECRET_VARIABLE, MS365_CLIENT_SECRET
                ),
                visible={"field": CONF_ENVIRONMENT_SECRET, "value": True},
            ): probatio.All(cv.string, probatio.Strip),
            probatio.Optional(
                CONF_ALT_AUTH_METHOD, default=entry_data[CONF_ALT_AUTH_METHOD]
            ): BooleanSelector(),
            probatio.Required(
                CONF_SERVICES, default=enabled_services(entry_data)
            ): SERVICES_SELECTOR,
            probatio.Optional(
                CONF_SHARED_MAILBOX,
                description={"suggested_value": entry_data.get(CONF_SHARED_MAILBOX)},
            ): cv.string,
            probatio.Required(CONF_API_OPTIONS): section(
                probatio.Schema(
                    {
                        probatio.Required(
                            CONF_API_COUNTRY,
                            default=country,
                        ): probatio.In(CountryOptions),
                        probatio.Optional(
                            CONF_TENANT_ID,
                            default=tenant_id if tenant_id != DEFAULT_TENANT_ID else "",
                        ): probatio.All(cv.string, probatio.Strip),
                    }
                ),
                {"collapsed": True},
            ),
        }

        return await self.async_step_user()

    def _check_existing(self, entity_name):
        config_entries = self.hass.config_entries.async_entries(DOMAIN)
        return any(
            config_entry.data.get(CONF_ENTITY_NAME) == entity_name
            for config_entry in config_entries
        )

    async def _async_delete_unreadable_token(self, auth_error, token_backend):
        # A reconfigure replaces the token, so one that cannot be read is deleted
        if (
            auth_error in [TOKEN_FILE_CORRUPTED, TOKEN_FILE_OUTDATED]
            and self._reconfigure
            and self._ms365account.account
        ):
            await self.hass.async_add_executor_job(token_backend.delete_token)
            return False
        return auth_error

    @callback
    def async_remove(self) -> None:
        """Remove the flow from the authorization callbacks."""
        if self._callback_urls is not None and self._flow:
            self._callback_urls.pop(self._flow["state"], None)


class MS365OptionsFlowHandler(OptionsFlow):
    """Options flow: a menu of the enabled services that have options.

    The options flow of each service (taken from upstream) runs unchanged as
    a delegate. Its step ids are prefixed with the service name so the
    translations of the services do not collide, and the options it creates
    are stored under the service name.
    """

    def __init__(self, entry: MS365ConfigEntry) -> None:
        """Initialise the options flow."""
        self._services = [
            name
            for name in enabled_services(entry.data)
            if SERVICE_DEFINITIONS[name].has_options
        ]
        self._delegate = None
        self._delegate_service = None

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:  # pylint: disable=unused-argument
        """Show the services menu."""
        if not self._services:
            return self.async_abort(reason="no_options")
        if len(self._services) == 1:
            return await self._async_start_service(self._services[0])
        return self.async_show_menu(step_id="init", menu_options=self._services)

    async def _async_start_service(self, service: str, user_input=None):  # pylint: disable=unused-argument
        self._delegate_service = service
        self._delegate = _build_service_options_flow(self, service)
        return await self._delegate.async_step_init()

    def __getattr__(self, name: str):
        """Route service steps (menu choices and prefixed steps) to delegates."""
        if not name.startswith("async_step_"):
            raise AttributeError(name)
        step = name.removeprefix("async_step_")
        services = self.__dict__.get("_services", [])
        if step in services:
            return ft.partial(self._async_start_service, step)
        delegate = self.__dict__.get("_delegate")
        service = self.__dict__.get("_delegate_service")
        if delegate is not None and step.startswith(f"{service}_"):
            return getattr(delegate, f"async_step_{step.removeprefix(f'{service}_')}")
        raise AttributeError(name)


def _build_service_options_flow(outer: MS365OptionsFlowHandler, service: str):
    """Instantiate the options flow of a service, wired to the outer flow."""
    base = SERVICE_DEFINITIONS[service].config_flow.MS365OptionsFlowHandler
    view = MS365ServiceEntry(outer.config_entry, service)

    class _ServiceOptionsFlow(base):
        """Service options flow running inside the unified options flow."""

        @property
        def config_entry(self):
            return view

        @callback
        def async_show_form(self, *, step_id=None, **kwargs):
            return outer.async_show_form(step_id=f"{service}_{step_id}", **kwargs)

        @callback
        def async_create_entry(self, *, data, **kwargs):
            options = deepcopy(dict(outer.config_entry.options))
            options[service] = dict(data or {})
            return outer.async_create_entry(data=options, **kwargs)

        @callback
        def async_abort(self, *, reason, **kwargs):
            return outer.async_abort(reason=reason, **kwargs)

    delegate = _ServiceOptionsFlow(view)
    delegate.hass = outer.hass
    delegate.handler = outer.handler
    delegate.flow_id = outer.flow_id
    delegate.context = outer.context
    return delegate


def get_callback_url(hass: HomeAssistant, alt_config, user_input):
    """Get the callback URL."""
    if alt_config:
        return f"{get_url(hass, prefer_external=True)}{AUTH_CALLBACK_PATH_ALT}"

    country = user_input[CONF_API_OPTIONS][CONF_API_COUNTRY]
    return COUNTRY_URLS[country][OAUTH_REDIRECT_URL]


@callback
def _async_get_callback_urls(hass: HomeAssistant):
    """Get the returned urls and register the callback view for this flow."""
    token_urls = hass.data.setdefault(AUTH_CALLBACK_DATA, {})
    # A view registered later at this path takes it over, so register for every flow
    hass.http.register_view(MS365AuthCallbackView(token_urls))
    return token_urls


class MS365AuthCallbackView(HomeAssistantView):
    """M365 Authorization Callback View."""

    requires_auth = False
    url = AUTH_CALLBACK_PATH_ALT
    name = AUTH_CALLBACK_NAME

    def __init__(self, token_urls) -> None:
        """Initialize."""
        self.token_urls = token_urls

    async def get(self, request):
        """Receive authorization token."""
        state = request.query.get("state")
        if state in self.token_urls:
            self.token_urls[state] = str(request.url)
            return web_response.Response(
                headers={"content-type": "text/html"},
                text="<script>window.close()</script>This window can be closed",
            )

        return web_response.Response(
            headers={"content-type": "text/html"},
            text="<script>window.close()</script>Invalid call to /api/ms365",
        )
