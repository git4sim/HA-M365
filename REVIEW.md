# Review of the MS365-* integrations

Review done while merging MS365-Calendar, -ToDo, -Mail, -Teams and -Contacts
(versions and commits in [UPSTREAM.md](UPSTREAM.md)) into one integration.
Before merging, all 425 upstream tests passed on Home Assistant 2026.11.1.

Overall the code base is in good shape: a clean split into a shared core and an
`integration` package per service, config entries with subentries, repairs
issues, diagnostics with redaction, a lockable token backend and thorough
tests. The findings below are ordered by severity.

## Fixed in this repository

### Security

1. **Any readable file could be mailed out** (Mail: `notify`, `mail_send`,
   `photos`). `_get_ha_filepath` accepted every path, so anyone allowed to call
   an action (non-admin users can) could send e.g. `/config/secrets.yaml` or the
   token files to any address. Files now have to be in
   `allowlist_external_dirs` (`hass.config.is_allowed_path`), like core
   integrations do. *Breaking*: users attaching files from `/config/…` must add
   the directory to the allowlist.
   `services/mail/utils_integration.py`, test `tests/mail/integration/test_attachment_security.py`.
2. **Zip archive written to a caller-chosen path.** `zip_name` was used as is,
   relative to the process working directory (`../../x.zip` worked). The archive
   is now created in a private temp directory with the base name only.
3. **Attachment names from incoming mail used as file names.** With
   `save_attachments` a name containing `/` made every update of the mail
   sensor fail (the sensor stays unavailable while that mail is among the
   fetched items – anyone who can send a mail can trigger it); names are now
   sanitised.
   `services/mail/filemgmt_integration.py`.

### Bugs

4. **`contacts_search` used the wrong account with several entries.** The
   action was registered on every entry set-up, so the account set up last
   answered all calls. It is now registered once and takes an optional
   `config_entry_id` (required when more than one account has Contacts).
5. **Double reload after the To Do / Teams options flow.** The flows called
   `async_reload` *before* the new options were saved and the update listener
   then reloaded again (Calendar already had the correct pattern, which is now
   used for To Do; Teams relies on the listener).
6. **No reauth step.** Setup raises `ConfigEntryAuthFailed`, which makes Home
   Assistant offer *Reauthenticate*, but there was no `async_step_reauth`;
   reauth now runs the reconfigure flow. (Home Assistant now also shows its
   standard reauth notice next to the integration's more detailed repair issue.)
7. **Diverged core helper.** `helpers/utils.py` was the only core file that
   differed: `async_check_personal_account` took a token backend in Calendar
   and a coordinator in the other four, and crashed there on a token without
   account. To Do now uses `runtime_data.personal_account`, which is computed
   once at set-up.
8. **Blocking I/O in the event loop**: the token file existence check ran in
   the loop at every set-up; it now runs in the executor.
9. **Translations that never matched a field**: `client_sec_environment_variable`
   (field is `client_sec_variable`) and the mail subentry `from_address`
   (field is `from`) – the labels were missing in the UI.
10. Calendar's `not_authorised` message used a different template than the
    other services (a shared translation key cannot serve both); unified.

### Cleanup

11. `helpers/config_entry.py` was an unused duplicate of `classes/config_entry.py`.
12. Runtime data fields were annotated with the builtin `any` instead of `typing.Any`.
13. Copy-paste docstrings ("Configuration flow for the skyq platform") and
    the `INRTEGRATION_CONFIG_MINOR_VERSION` typo (constants no longer used).

## Product-level changes of the merge

* One config entry per **account**; services are enabled per entry. One app
  registration, one sign-in, one token (`m365_<account>.token`); the requested
  Graph scopes are the union of the enabled services.
* Config flow: account → per-service sections → authorise. Reconfigure can add
  or remove services; removed services' entities, mail subentries, YAML files
  and options are cleaned up.
* Options flow: a menu of the services with options; each upstream options
  flow runs unchanged as a delegate (steps prefixed with the service name).
* Own domain `m365` and storage folder `m365_storage`, so it can be installed
  next to the upstream integrations. The alternate auth callback stays
  `/api/ms365`, so existing app registrations keep working.

## Open recommendations (not changed)

* **Legacy notify platform.** Mail loads `notify` via
  `discovery.async_load_platform` on every entry set-up/reload. Home Assistant
  recommends `NotifyEntity`; `m365.mail_send` already covers the use case, the
  legacy service could be deprecated.
* **Actions registered in platform set-up.** Entity actions are registered per
  entry in `async_setup_entry` of the platforms; the HA quality scale
  (`action-setup`) wants them in `async_setup`, so they exist (and fail with a
  clear error) while an entry is not loaded.
* **Token file permissions.** Tokens (including refresh tokens) are written with
  the default umask; `0600` would be safer.
* **HTML in outgoing mails.** Photo URLs are inserted into `<img src="…">`
  without escaping (only callers of the action can inject, low risk).
* **Personal accounts and Teams.** Teams is not available for personal accounts;
  the flow could detect this (`personal_account`) and hide/deny the service.
