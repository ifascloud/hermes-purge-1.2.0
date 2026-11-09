# hermes-purge 1.2.0

Hermes Agent execution-posture plugin, exported from a local installation.

## Privacy

This package includes two generic policy rule files in `rules/`, covering confirmation, privacy, external writes, destructive operations, and factual verification. The export does not include live state, snapshots, Hermes configuration, credentials, or machine-specific paths.

## Contents

- Native plugin source: `plugin.yaml`, `__init__.py`, `purge_core.py`, `purge_commands.py`
- Packaged defaults: `rules/*.md`
- Bundled Hermes skill: `skills/hermes-purge/SKILL.md`
- Optional desktop status panel source: `desktop-panel/plugin.js` (not installed automatically)
- `install.ps1` and `install.sh`: copy the package into a durable Hermes source directory, validate it, then install it

## Install

Read the two files in `rules/` first. Extract or clone this repository, then run one installer from the package root.

PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Bash (Git Bash, macOS, or Linux):

```bash
bash ./install.sh
```

The installer creates `$HERMES_HOME/src/hermes-purge-export-1.2.0`, validates the plugin, then installs/enables it. It stops without changing anything if a `hermes-purge` plugin is already installed. Existing live rule edits are not overwritten by the plugin's first-load seeding. To update an existing installation, review that install's source and use `hermes plugins update hermes-purge` where configured, or remove the old plugin deliberately before running this installer. The plugin data under `$HERMES_HOME/purge/` survives plugin removal.

For a manual install, first make a Git repository copy at a durable path (Hermes `file://` installs clone a Git URL), then run:

```text
hermes plugins validate <plugin-directory>
hermes plugins install file:///<absolute-plugin-path> --enable
```

## Commands

Use `/purge` in chat or `hermes purge` in a terminal:

- `status`, `doctor`, `rules`, `show`
- `on`, `off`, `apply`
- `snapshot [label]`, `snapshots`, `restore <id>`, `diff [id]`

Rules are loaded from `$HERMES_HOME/purge/rules/*.md`, sorted by filename. Edit the live files there; packaged defaults only seed missing files and do not overwrite existing edits. Rules are rendered at session start, so start a new session with `/new` after changing them.

## Acceptance checks

| Check | Expected |
|---|---|
| `hermes plugins validate <source-dir> --json` | `"ok": true` |
| `hermes plugins doctor <source-dir> --ci` | Runtime import and registration pass |
| `/purge doctor` in a loaded chat session | Five layers report ready |
| `/purge rules` | Lists rule files and SHA-256 hashes |
| `/new`, then `/purge show` | Updated rendered rules appear |

The desktop panel is optional and opt-in. To use it, copy `desktop-panel/plugin.js` to `$HERMES_HOME/desktop-plugins/hermes-purge/plugin.js`; it is intentionally not enabled by the installers.

## Remove

Disable or remove the plugin with `hermes plugins disable hermes-purge` or `hermes plugins remove hermes-purge`. Plugin data under `$HERMES_HOME/purge/` is kept after plugin removal; remove it separately only if you also intend to discard local rules, state, and snapshots.

## Portability notes

The displayed `max_turns`, approval mode, and default model come from the receiving machine's own `config.yaml`. Different values are expected. Prompt sections are frozen at session start. The plugin does not edit Hermes core or change approval settings.
