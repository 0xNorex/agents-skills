---
name: dms-shell
description: Control local DankMaterialShell audio, brightness, wallpaper, theme, notifications and shell widgets. Window/workspace management and screenshots use niri.
---

# DankMaterialShell

Use `dms --help` and `dms ipc --help` to verify the installed command surface. A live shell is required for IPC; installed CLI does not prove a running shell. If target discovery fails, report it instead of assuming commands succeeded.

Examples below are separate commands, not a script to execute in full. Use only the action requested. Check a target's supported functions when a version differs; do not blindly retry a state-changing toggle.

## Notifications

```bash
dms notify "Title" "Body"
dms ipc call toast info "message"
dms ipc call notifications getDoNotDisturb
dms ipc call notifications toggleDoNotDisturb
```

## Audio and display

```bash
dms ipc call mpris list
dms ipc call mpris playPause
dms ipc call mpris setvolume 50
dms ipc call mic status
dms ipc call mic mute
dms brightness get
dms brightness set 70 --mon all
dms ipc call night status
dms ipc call night setTargetTemp 4000
dms ipc call powerprofile list
dms ipc call powerprofile set performance
```

Other playback operations, where supported: `play`, `pause`, `next`, `previous`; invoke each as the function after `mpris`, not as shell pipes.

## Theme and shell UI

```bash
dms ipc call wallpaper set ~/Pictures/w.jpg
dms ipc call theme getMode
dms ipc call theme dark
dms ipc call launcher openQuery "firefox"
dms ipc call notepad open
dms ipc call dock status
dms ipc call lock isLocked
dms ipc call lock lock
dms ipc call powermenu open
```

Clipboard: use installed `wl-copy`/`wl-paste` only for the requested content. Window control and screenshots: [niri](../niri/SKILL.md). Do not inject keystrokes into an unidentified focused window.

Prefer explicit setters and verify resulting state when a query exists. Lock, logout, reboot, shutdown and profile changes need a clear user request; opening a power menu is not consent to select an action. Do not restart the shell or read clipboard contents as routine diagnostics.
