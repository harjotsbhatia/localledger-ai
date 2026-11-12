# Security

LocalLedger handles sensitive financial data. This document states what is protected, how,
and what is not.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting on this
repository. Include steps to reproduce. Never attach real financial data.

## Threat model

**Assets:** transaction history, the database key, the per-launch API token, future bank tokens.

| # | Threat | Mitigation | Residual risk |
|---|---|---|---|
| 1 | A website in the user's browser calls the local API | Random port; bearer token required on every route; CORS allows only the app origin; no cookies, so no ambient authority | None known |
| 2 | DNS rebinding (hostile name resolving to 127.0.0.1) | Host header must be `127.0.0.1` or `localhost`; token still required | None known |
| 3 | Another local process run by a different user | Loopback bind, token, database file mode `0600`, directory `0700` | — |
| 4 | Malware running **as the same user** | Token is passed over stdin, not argv or environment. Not a defense against a determined same-user attacker, who can read process memory or prompt for Keychain access | **Accepted.** Out of scope, as for most desktop apps |
| 5 | Disk theft, backups, other apps reading the data file | SQLCipher (AES-256) with a random 256-bit key held in the macOS Keychain | Data is readable while the Mac is unlocked and the user is logged in |
| 6 | Prompt injection in merchant names, CSV content | Statement text reaches the model only inside tool results; system prompt marks them as data; tools are read-only and take typed arguments; no SQL, shell, file or network tool exists | A model can still be misled into a wrong *sentence*. Amounts are checked against tool output and lookups are always displayed |
| 7 | Model invents numbers | Grounding check flags amounts not produced by a tool; replies are discarded when every lookup failed | Dates and wording are not verified |
| 8 | Financial data sent to a cloud AI | Ollama URL must be a loopback address; no other AI provider exists | A user-installed Ollama configured to proxy elsewhere is outside our control |
| 9 | Sensitive data in logs | Logging policy: counts, ids, durations only; access log disabled; test asserts imports log no transaction text | Policy relies on review for new code |
| 10 | Malicious CSV | Size and row limits; strict amount/date parsing; values stored as text and bound as SQL parameters; React escapes output | Formula injection matters only if data is later exported to a spreadsheet (no export exists) |
| 11 | Supply chain | Lockfiles committed (`uv.lock`, `pnpm-lock.yaml`, `Cargo.lock`); small dependency set | No automated audit yet |
| 12 | Webview compromise (XSS) | Strict CSP (`script-src 'self'`, `connect-src` limited to loopback and IPC); the webview has no filesystem, shell or HTTP plugin; only three IPC commands | An XSS could call the local API with the token for the session |

## Design decisions

- **No silent fallback to plaintext.** If SQLCipher is unavailable the backend refuses to
  start. `LOCALLEDGER_INSECURE_DEV_DB=1` enables plain SQLite for development; the UI then
  shows a permanent "Storage is NOT encrypted" banner. It is not equivalent protection.
- **Raw key, not a passphrase.** The key is 32 random bytes, so there is no password to
  brute-force and no KDF cost per connection. Losing the Keychain item loses the data.
- **Read-only AI.** The first release exposes no tool that writes, moves money or reaches
  the network.
- **Deleting data** removes all rows and vacuums the database. The Keychain key remains.

## Network policy

The backend makes outbound connections only to the configured Ollama URL, which must be
loopback. Offline mode additionally blocks model downloads. There is no telemetry.

## Bank connectivity (not implemented)

When a bank aggregator is used, transaction data passes through that provider's servers.
LocalLedger will not claim otherwise.

**Open blocker for Plaid bring-your-own-credentials:** Plaid's API expects `client_secret`
and access tokens to be held by a server the developer controls. A desktop app that stores a
user's own Plaid secret in the Keychain may not meet Plaid's security and compliance
requirements, and production access requires Plaid's review. This must be checked against
Plaid's current documentation and terms before any production BYO-credentials work. Sandbox
integration is planned first. LocalLedger will never ask for bank passwords or scrape bank sites.

## Distribution status

Release bundles are currently **ad-hoc signed and not notarized**. Hardened runtime,
Developer ID signing and notarization are Phase 4. Two things to settle then: entitlements
for the PyInstaller sidecar, and Keychain access for a signed identity (an unsigned or
re-signed binary may trigger a macOS Keychain prompt when reading a key created by a
different binary).
