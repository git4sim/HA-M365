"""Shim that lets the upstream single-service flow tests drive the unified flow.

The upstream MS365-* integrations used a one-page config flow with the service
settings on the account page and un-prefixed options flow step ids. The
unified integration asks for the services on the account page and their
settings on a separate ``services`` step, and prefixes the options flow steps
with the service name. This shim translates between the two so the upstream
test suites keep exercising the same behaviour.
"""

from copy import deepcopy
from typing import Any

from custom_components.m365.classes.service_entry import build_service_data
from custom_components.m365.const import CONF_SERVICES
from custom_components.m365.services import SERVICE_DEFINITIONS


def _service_keys(service: str) -> set[str]:
    definition = SERVICE_DEFINITIONS[service]
    keys = {str(key) for key in definition.config_schema()}
    keys |= {
        str(key)
        for key in definition.config_flow.integration_reconfigure_schema(
            _AnyDefault()
        )
    } - {"shared_mailbox"}
    return keys


class _AnyDefault(dict):
    """Mapping returning None for every key (to enumerate schema keys)."""

    def __getitem__(self, key):
        return None

    def get(self, key, default=None):
        return default


def _split(user_input: dict, service: str) -> tuple[dict, dict]:
    keys = _service_keys(service)
    account = {k: v for k, v in user_input.items() if k not in keys}
    service_part = {k: v for k, v in user_input.items() if k in keys}
    return account, service_part


def _strip_prefix(result: Any, service: str) -> Any:
    if isinstance(result, dict) and isinstance(result.get("step_id"), str):
        prefix = f"{service}_"
        if result["step_id"].startswith(prefix):
            result = dict(result)
            result["step_id"] = result["step_id"].removeprefix(prefix)
    return result


def install(hass, service: str) -> None:
    """Install the shim on the flow managers of hass."""
    flow_manager = hass.config_entries.flow
    configure = flow_manager.async_configure
    pending: dict[str, dict] = {}

    async def _async_configure(flow_id, user_input=None):
        flow = flow_manager._progress.get(flow_id)  # noqa: SLF001
        step_id = (getattr(flow, "cur_step", None) or {}).get("step_id")
        if user_input is None or step_id not in ("user", "services"):
            return await configure(flow_id, user_input)
        if step_id == "user" and CONF_SERVICES in user_input:
            return await configure(flow_id, user_input)

        account, service_part = _split(deepcopy(dict(user_input)), service)
        if step_id == "user":
            account[CONF_SERVICES] = [service]
            pending[flow_id] = account
            result = await configure(flow_id, account)
            if result.get("step_id") != "services" or result.get("errors"):
                return result
        if step_id == "services":
            # The upstream tests resubmit the whole page after an error; the
            # account part of the unified flow was already submitted, so
            # apply changed account settings to the flow directly.
            flow._user_input.update(  # noqa: SLF001
                {k: v for k, v in account.items() if k != CONF_SERVICES}
            )
            pending[flow_id] = {**pending.get(flow_id, {}), **account}
        result = await configure(flow_id, {service: service_part})
        if result.get("step_id") == "services" and result.get("errors"):
            # Report validation errors where the upstream flow reported them
            flat = build_service_data(
                {**pending.get(flow_id, {}), CONF_SERVICES: {service: service_part}},
                service,
            )
            result = dict(result)
            result["step_id"] = "user"
            result["errors"] = SERVICE_DEFINITIONS[service].validate(flat) or dict(
                result["errors"]
            )
        return result

    flow_manager.async_configure = _async_configure

    options_manager = hass.config_entries.options
    options_init = options_manager.async_init
    options_configure = options_manager.async_configure

    async def _async_options_init(*args, **kwargs):
        return _strip_prefix(await options_init(*args, **kwargs), service)

    async def _async_options_configure(*args, **kwargs):
        return _strip_prefix(await options_configure(*args, **kwargs), service)

    options_manager.async_init = _async_options_init
    options_manager.async_configure = _async_options_configure


def integration_issues(issue_registry) -> dict:
    """Return the repair issues of the integration itself.

    The unified integration supports reauth, so Home Assistant adds its own
    ``config_entry_reauth`` issue next to the integration's detailed issue.
    """
    return {key: issue for key, issue in issue_registry.issues.items() if key[0] != "homeassistant"}
