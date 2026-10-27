---
name: niri
description: Manage local niri windows, workspaces and monitors, or capture screenshots. DMS theme, wallpaper, audio and notifications belong to dms-shell.
---

# niri control

Use `niri msg`; `-j` provides JSON for queries. Commands run as the desktop user and need a live session. Check `niri msg action --help` or the chosen action's `--help` before relying on version-specific options.

## Query and target

```bash
niri msg -j windows
niri msg -j workspaces
niri msg -j outputs
niri msg -j focused-window
```

Select the matching window ID from current state; re-query after spawning or closing windows. Do not guess the active target.

## Actions (substitute the requested target)

```text
niri msg action focus-window --id <ID>
niri msg action close-window --id <ID>
niri msg action fullscreen-window --id <ID>
niri msg action move-window-to-workspace <name-or-index> --id <ID>
niri msg action focus-workspace <name-or-index>
niri msg action set-column-width <width>
niri msg action set-window-height <height>
niri msg action toggle-overview
```

Other column, monitor and layout operations are listed by the installed help; do not treat slash-separated alternatives as executable commands. `do-screen-transition` is a visual transition, not the overview toggle.

## Screenshots

When `--path` is supported, provide an explicit absolute output path:

```bash
niri msg action screenshot-screen --path /tmp/niri-screen.png
```

Then view the file with the image-reading tool. Otherwise consult the configured `screenshot-path`; do not assume `~/Pictures/Screenshots` or infer success from an unrelated recent file. Use screenshot-window or the interactive picker only when that scope matches the request.

Screenshots may include private content; do not upload them without permission. Closing windows, ending the session, launching commands and changing monitor state require a clear requested action. Verify resulting state; don't leave an unbounded event stream running for a one-shot task.
