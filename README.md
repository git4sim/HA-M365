# Microsoft 365 for Home Assistant

One integration for Microsoft 365 in Home Assistant: **Calendar, To Do, Mail,
Teams and Contacts** with a single Entra ID app registration, a single sign-in
and a single token per account.

It merges the excellent but separate `MS365-*` integrations by
[RogerSelwyn](https://github.com/RogerSelwyn) into one product. The service
code is kept close to upstream (see [UPSTREAM.md](UPSTREAM.md)); the review
done while merging and the fixes made are in [REVIEW.md](REVIEW.md).

| Service  | Provides                                                                      |
|----------|-------------------------------------------------------------------------------|
| Calendar | `calendar.*` entities, create/modify/remove/respond to events, group calendars |
| To Do    | `todo.*` entities, tasks and checklist items                                  |
| Mail     | `sensor.*` per mail folder (subentries), auto reply sensor/actions, `m365.mail_send`, `notify.m365_<account>` |
| Teams    | presence and latest chat sensors, send chat messages, set presence (work/school accounts only) |
| Contacts | `m365.contacts_search` action                                                  |

## Installation

1. HACS → three dots → *Custom repositories* → add this repository
   (category *Integration*), then install **Microsoft 365**.
   Or copy `custom_components/m365` into your `config/custom_components`.
2. Restart Home Assistant.

Requires Home Assistant 2026.11 or newer.

## Entra ID app registration

The app registration is the same as for the upstream integrations, an existing
one can be reused.

1. [Entra admin center](https://entra.microsoft.com) → *App registrations* → *New registration*.
   Supported account types: *Accounts in any organizational directory and personal
   Microsoft accounts* (or single tenant – then enter the tenant ID under
   *Advanced API options*).
2. *Authentication* → *Add a platform* → *Web*, redirect URIs:
   * `https://login.microsoftonline.com/common/oauth2/nativeclient` (default method)
   * `https://<your external HA URL>/api/ms365` (only for the *alternate* method)
3. *Certificates & secrets* → new client secret → copy the **Value** (not the ID).
4. *API permissions* → *Microsoft Graph* → *Delegated* – add the permissions of the
   services you want (see below). The integration only *requests* what the enabled
   services need.

### Permissions per service

| Service  | Read only                                  | With "update" options                                      |
|----------|--------------------------------------------|------------------------------------------------------------|
| (always) | `User.Read`                                |                                                            |
| Calendar | `Calendars.Read` (`Calendars.ReadBasic` for *basic calendar*) | `Calendars.ReadWrite`                   |
| Calendar groups | `Group.Read.All`                    | `Group.ReadWrite.All`                                      |
| To Do    | `Tasks.Read`                               | `Tasks.ReadWrite`                                          |
| Mail     | `Mail.Read`                                | `Mail.Send`; auto reply: `MailboxSettings.ReadWrite`       |
| Teams    | `Chat.Read`, `Presence.Read`               | `Chat.ReadWrite`, `Presence.ReadWrite`; other user's status: `Presence.Read.All`, `User.ReadBasic.All` |
| Contacts | `Contacts.Read`                            |                                                            |

With a shared mailbox, Calendar/Mail/Contacts permissions get the `.Shared`
suffix (e.g. `Calendars.Read.Shared`).

## Setup

*Settings → Devices & services → Add integration → Microsoft 365*

1. **Account** – a name for the account (used in entity ids, e.g. `work`),
   client ID and secret (or the name of an environment variable holding it),
   the services to enable and optionally a shared mailbox.
2. **Service settings** – one section per selected service (enable update
   actions, auto reply, Teams sensors, …).
3. **Authorise** – open the link, sign in, and paste the URL you are sent to
   (default method), or let Home Assistant receive it (alternate method).

Add one entry per Microsoft 365 account. Later changes:

* **Reconfigure** – enable/disable services or change their settings. Removing
  a service removes its entities; a new sign-in requests the new permissions.
* **Configure** (options) – a menu with the services that have options:
  Calendar (which calendars, sync window), To Do (which lists, limits),
  Teams (update interval).
* **Mail folders** – *Add mail folder* on the integration page (subentries).

Calendars and To Do lists are stored in
`config/m365_storage/m365_calendars_<account>.yaml` and
`m365_todos_<account>.yaml` and can be edited there as upstream.

## Actions and events

All actions are in the `m365` domain, e.g. `m365.create_calendar_event`,
`m365.new_todo`, `m365.mail_send`, `m365.send_chat_message`,
`m365.contacts_search`. Events are fired as `m365_<event>`, e.g.
`m365_create_calendar_event`, `m365_new_todo`, `m365_completed_todo`.

Files sent with `m365.mail_send` / `notify.m365_<account>` must be in a
directory listed in
[`allowlist_external_dirs`](https://www.home-assistant.io/integrations/homeassistant/#allowlist_external_dirs).

The upstream documentation of the individual services applies otherwise:
<https://rogerselwyn.github.io/MS365-HomeAssistant/>.

## Migrating from the MS365-* integrations

The integrations can be installed side by side (different domain, token and
YAML files), but entity ids would clash, so:

1. Note the account name you used and remove the `MS365 Calendar/To Do/Mail/Teams/Contacts`
   entries.
2. Add **Microsoft 365** with the same account name and app registration and
   enable the services you used. Copy `config/ms365_storage/ms365_calendars_<name>.yaml`
   to `config/m365_storage/m365_calendars_<name>.yaml` (same for `todos`) to keep
   calendar/list settings.
3. Update automations: `ms365_calendar.*`/`ms365_todo.*`/… actions → `m365.*`,
   events `ms365_<service>_<event>` → `m365_<event>`, `notify.ms365_mail_<name>` → `notify.m365_<name>`.

## Development

```bash
uv venv -p 3.14 && uv pip install -r requirements_test.txt ruff==0.17.4
```

```bash
for suite in unified calendar todo mail teams contacts; do uv run pytest tests/$suite -n auto; done
```

```bash
uv run ruff check .
```

`tests/unified` tests the combined integration; `tests/<service>` are the
upstream suites, run against this integration.

## Credits

All service functionality comes from RogerSelwyn's MS365 integrations and
the [python-o365](https://github.com/O365/python-o365) library. MIT licensed.
