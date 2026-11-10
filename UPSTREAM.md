# Upstream sources

This integration merges the Microsoft 365 integrations for Home Assistant by
[RogerSelwyn](https://github.com/RogerSelwyn) (MIT licensed, originally based
on the O365 integration by Patrick Toft Steffensen) into a single integration.

| Service  | Upstream repository                                                   | Version | Commit    | Package here                          |
|----------|-----------------------------------------------------------------------|---------|-----------|---------------------------------------|
| Calendar | [MS365-Calendar](https://github.com/RogerSelwyn/MS365-Calendar)       | v1.14.0 | `5ba263d` | `custom_components/m365/services/calendar` |
| To Do    | [MS365-ToDo](https://github.com/RogerSelwyn/MS365-ToDo)               | v1.14.1 | `1070d5e` | `custom_components/m365/services/todo`     |
| Mail     | [MS365-Mail](https://github.com/RogerSelwyn/MS365-Mail)               | v1.15.0 | `a11c94b` | `custom_components/m365/services/mail`     |
| Teams    | [MS365-Teams](https://github.com/RogerSelwyn/MS365-Teams)             | v1.14.0 | `6f3f86a` | `custom_components/m365/services/teams`    |
| Contacts | [MS365-Contacts](https://github.com/RogerSelwyn/MS365-Contacts)       | v1.14.0 | `cd4a2a8` | `custom_components/m365/services/contacts` |

The shared core (`classes/`, `helpers/`, `const.py`, `schema.py`) was identical
in all five repositories (apart from `helpers/utils.py`, see `REVIEW.md`) and
was taken from MS365-Calendar.

## Porting upstream changes

Each `services/<name>` package is the upstream `integration/` package with
only these mechanical changes:

* relative imports of the core go one level deeper (`..const` → `...const`),
* `DOMAIN` is `"m365"`, YAML files are named `m365_calendars_<name>.yaml` /
  `m365_todos_<name>.yaml`,
* the fixes listed in `REVIEW.md` (marked with a comment in the code).

So an upstream fix in e.g. `MS365-ToDo/custom_components/ms365_todo/integration/todo_integration.py`
can usually be applied to `services/todo/todo_integration.py` with
`git apply --directory` / `patch -p` after adjusting the path. The upstream
test suites live in `tests/<service>` and run against the unified integration
(`tests/unified_shim.py` translates the upstream config flow tests).
