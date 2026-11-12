# ADR 0001: Python sidecar on loopback with per-launch token

**Status:** accepted

**Context.** The UI (webview) needs the Python backend. Any localhost HTTP server can be
reached by other websites and local processes.

**Decision.** The Rust shell picks a free port, generates a 256-bit token from
`/dev/urandom`, starts the sidecar, and writes the token to its stdin. The UI gets the port
and token through Tauri IPC once the port accepts connections. The backend requires
`Authorization: Bearer`, checks the Host header, and allows CORS only for the app origin.

**Alternatives.** Unix domain socket (webviews cannot fetch from one); Tauri IPC for
everything (would move all logic into Rust or require a proxy layer); token in an
environment variable (visible to same-user `ps`).

**Consequences.** One extra hop per request and a CORS preflight. A same-user attacker is
still out of scope. The sidecar watches the parent pid and exits when the app does.
