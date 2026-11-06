# NotifyEcho for Mainsail

Klipper / Moonraker notifications through [NotifyEcho](https://notifyecho.com).

This is a **Moonraker component** plus a small settings page linked from
Mainsail's sidebar. Mainsail has no plugin system, so the page uses Mainsail's
supported custom-navigation feature and is served by Moonraker itself.

## What it does

```
Klipper job state ─┐
Klippy ready ──────┼─► Moonraker component ─► POST {notifyecho}/api/notify/{workflowId}
virtual_sdcard ────┘
```

Each configured event sends a normal NotifyEcho request with a
`klipper.*` kind and the full Klipper event data in `content.data` and
`metadata`.

## Install

Install the latest tagged release:

```sh
curl -fsSL https://github.com/iamajoe/notifyecho_mainsail/releases/latest/download/install.sh | bash
```

Install a specific release:

```sh
curl -fsSL https://github.com/iamajoe/notifyecho_mainsail/releases/download/vX.Y.Z/install.sh | bash
```

Or clone a tag and run the installer:

```sh
git clone --branch vX.Y.Z https://github.com/iamajoe/notifyecho_mainsail.git
cd notifyecho_mainsail
./install.sh --tag vX.Y.Z
```

Only tagged releases are supported. The installer always checks out a release
tag; installing or running from `main` is not supported.

Options:

```sh
./install.sh --help
```

The installer:

1. Clones/updates the repository at `~/notifyecho_mainsail` and checks out the
   chosen release tag.
2. Symlinks the component into Moonraker's `components` directory.
3. Adds `[notifyecho]` and `[update_manager notifyecho]` to `moonraker.conf`.
4. Adds a **NotifyEcho** entry to `<config>/.theme/navi.json`.
5. Restarts Moonraker.

If `--tag` is omitted, the installer resolves the newest `vX.Y.Z` tag from the
repository. No settings are collected on the command line; everything is
configured in the UI.

## Configure

1. Open Mainsail.
2. Click **NotifyEcho** in the sidebar.
3. Enter:
   - NotifyEcho URL (default `https://notifyecho.com`)
   - Project bearer token
   - Default workflow ID
4. Press **Verify** to check the token + workflow combination.
5. Press **Send test** to send a real test event.
6. Use **Check for updates** / **Update** in the Updates card to keep the
   plugin current (see [Update](#update)).

### Routing modes

- **Default mode** — one workflow ID receives every enabled event.
- **Advanced mode** — each event may have its own workflow ID. Blank falls back
  to the default workflow ID.

You can reuse the same workflow ID for any number of events. To stop an event
from going out, disable it.

### Verify

The Verify button calls the existing NotifyEcho endpoint:

```http
GET {baseUrl}/api/notify/{workflowId}/status
Authorization: Bearer {token}
```

- `200` — valid token + workflow.
- `401` — invalid bearer token.
- `404` — workflow not found for that token.
- `429` — rate limited.

Verification runs server-side from Moonraker, so there are no CORS issues.

## Event kinds

Create matching triggers in NotifyEcho before enabling an event.

| Event | Kind |
| --- | --- |
| Print started | `klipper.job_state.started` |
| Print paused | `klipper.job_state.paused` |
| Print resumed | `klipper.job_state.resumed` |
| Print complete | `klipper.job_state.complete` |
| Print cancelled | `klipper.job_state.cancelled` |
| Print failed | `klipper.job_state.failed` |
| Print progress | `klipper.job_state.progress` |
| Printer ready | `klipper.ready` |
| Printer shutdown | `klipper.shutdown` |
| System error | `klipper.error` |

All events are enabled by default; each one can be disabled.

- `klipper.job_state.failed` means the print itself failed.
- `klipper.error` means a Klipper/Moonraker/plugin system error, including
  Klipper starting in an error state, an unexpected Klipper disconnect, and
  internal plugin failures.
- `klipper.job_state.progress` sends once per configured milestone per print.
  Default milestones: `25, 50, 75, 90`.

## Payload

Example for a completed print:

```json
{
  "kind": "klipper.job_state.complete",
  "content": {
    "title": "Print complete",
    "message": "benchy.gcode finished in 1h 12m on voron.",
    "data": {
      "event": "print_complete",
      "filename": "benchy.gcode",
      "printer": "voron",
      "state": "complete",
      "printDuration": 4321.2,
      "totalDuration": 4380.0,
      "filamentUsed": 12345.6,
      "layers": { "current": 120, "total": 120 }
    }
  },
  "metadata": {
    "source": "mainsail",
    "event": "print_complete",
    "kind": "klipper.job_state.complete",
    "printer": { "hostname": "voron", "port": 7125 },
    "printStats": {},
    "previousPrintStats": {},
    "timestamp": "2026-11-03T12:00:00Z"
  },
  "options": {
    "tags": ["klipper", "print_complete"]
  }
}
```

Workflows can render the event data with `{{content.data.*}}` or
`{{metadata.*}}`.

## Update

Updates are release-to-release and use Moonraker's update manager with
`channel: stable`. The NotifyEcho settings page has an **Updates** card that
shows the installed and remote versions, whether an update is available, and an
**Update** button. This is the same update path Mainsail uses under
**Machine → Update Manager**.

- Updates are **never automatic**. The user must press **Update**.
- Only installs checked out at a release tag can be updated. If the install is
  on a branch or commit, the Update button is disabled and the installer must be
  re-run from a release tag.
- Updating pulls the repository to a newer release tag and restarts Moonraker.

NotifyEcho has no runtime dependencies beyond Moonraker and the Python standard
library.

## Uninstall

```sh
./uninstall.sh
```

This removes the component symlink, config sections and navigation entry.
Use `--purge` to also delete the cloned repository. Settings remain in
Moonraker's database namespace `notifyecho`.

## Limitations

- Mainsail has no native plugin API. The settings page is a standalone page
  opened from Mainsail's sidebar, not a tab inside Mainsail's Settings dialog.
- The navigation link assumes Mainsail and Moonraker share an origin
  (`/server/notifyecho/ui`). If Moonraker uses a `route_prefix` or runs on a
  different host, edit `.theme/navi.json` and point `href` at the full URL.
- If Moonraker's authorization requires a JWT login, the page must be opened
  from the same authenticated browser session.

## Troubleshooting

- Check `~/printer_data/logs/moonraker.log` for `NotifyEcho`.
- Make sure `[notifyecho]` is present in `moonraker.conf` and Moonraker was
  restarted.
- The sidebar link only appears after Mainsail is reloaded.
- If the settings page is blank, verify that Moonraker serves
  `/server/notifyecho/ui`.
- If `Verify` returns `404`, the workflow ID does not exist in the project that
  owns the bearer token.
- If Moonraker requires authentication, open the page from the same browser
  session used for Mainsail.

## Security

- The bearer token is stored in Moonraker's SQLite database, like other
  Moonraker settings.
- Do not share the token; it grants access to the project's `/notify` endpoint.
- The settings page is protected by Moonraker's normal authorization.

## Development

Requires Python 3.9+ and `just`.

```sh
just test     # unit + integration tests
just lint     # ruff, compile, JS, bash and shellcheck (when available)
just build    # smoke-test the installer + dist/notifyecho_mainsail.tar.gz
just check    # lint + test
```

Run `just --list` for all recipes. CI runs the same checks on GitHub across
Python 3.9, 3.11 and 3.13.

### Releasing

Releases are published from semver tags. Push a tag and GitHub Actions runs the
release workflow:

```sh
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

The workflow validates the tag, runs the tests, builds the archive, and publishes
a GitHub Release with `install.sh`, `uninstall.sh` and
`dist/notifyecho_mainsail.tar.gz`. The latest `install.sh` is then available at:

```text
https://github.com/iamajoe/notifyecho_mainsail/releases/latest/download/install.sh
```

Layout:

```
install.sh
uninstall.sh
.github/workflows/
  ci.yml           lint + test on pull requests and pushes
  release.yml      publish tagged releases with install.sh
moonraker_component/notifyecho/
  component.py     Moonraker wiring, events, HTTP endpoints
  settings.py      settings defaults + validation
  payload.py       Klipper event -> NotifyEcho request
  progress.py      progress milestone tracking
  client.py        NotifyEcho HTTP client
  static/          settings page (no build step)
tests/
```

No runtime dependencies beyond Moonraker and the Python standard library.

## References

- Moonraker components: https://moonraker.readthedocs.io/en/latest/components/
- Mainsail custom navigation: https://docs.mainsail.xyz/features/custom-themes/custom-navigation/
- Moonraker job state events: https://github.com/Arksine/moonraker/blob/master/moonraker/components/job_state.py
- Moonraker update manager: https://moonraker.readthedocs.io/en/latest/configuration/#update_manager
- NotifyEcho `/notify` contract: `server/entities/notify.go` in the NotifyEcho repository
