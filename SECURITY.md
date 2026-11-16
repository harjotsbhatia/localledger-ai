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
| 13 | Bank credentials leak (SimpleFIN access URL, Plaid Sandbox secret and access token) | Stored only in the macOS Keychain, one item per connection; never written to the database, API responses or logs (tests assert each); cleared from UI state after submission; destroyed on disconnect and on delete-all-data | Same-user malware (see 4) |
| 14 | A provider response redirects the app to another host | Per-connector HTTPS host allow-list applied to every URL including ones the provider returns; redirects not followed; proxy environment ignored | A compromised provider can still send false data |
| 15 | Hostile text from a provider (account names, notices) | Stripped of control characters and length-limited; rendered as text; reaches the model only inside tool results | As for 6 |
| 16 | Exceeding a provider's usage limits and losing access | SimpleFIN syncs limited locally to one per hour (the Bridge asks for 24 or fewer a day) | Manual syncing across several installs sharing a token is not coordinated |

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

Outbound connections are limited to:

1. the configured Ollama URL, which must be loopback;
2. for a SimpleFIN connection, HTTPS hosts under `simplefin.org`;
3. for a Plaid Sandbox connection, `https://sandbox.plaid.com` only.

Items 2 and 3 happen only after the user adds a connection and acknowledges where the data
travels. Offline mode blocks model downloads and every provider call. There is no telemetry.

## Bank connectivity

When a bank-data provider is used, transaction data passes through that provider's servers.
LocalLedger does not claim otherwise, and the connect screen says which provider sees the data.

**SimpleFIN Bridge.** The user creates a setup token at the Bridge; the app exchanges it once
for a read-only access URL. The bank password never reaches the app. Access can be revoked
only on the Bridge website, so disconnecting removes the local credentials and says so. A
rejected token is reported with the Bridge's warning that someone else may have claimed it.

**Plaid: Sandbox only.** The connector creates items with the Sandbox-only
`/sandbox/public_token/create` endpoint, so no Plaid Link script is loaded and the app's
content security policy is unchanged. The host is fixed in code; there is no setting that
selects production.

**Why Plaid production is not offered (open blocker).** Checked against Plaid's documentation
and developer policy (effective 2026-04-19):

- The policy makes the developer solely responsible for the confidentiality of the client ID
  and secret and forbids sharing them with third parties. It does not address a desktop app
  in which each user supplies their own keys.
- Production access requires Plaid's review of the application and use case.
- Real items require Plaid Link. In a desktop app that means loading Plaid's script into the
  webview or using Hosted Link, whose completion is reported by webhook or by polling.
- End-user data must be encrypted in storage and transit, which this app does, but that alone
  does not settle the points above.

Until Plaid confirms that a bring-your-own-keys desktop model is acceptable, production
support should not be added. LocalLedger will never ask for bank passwords or scrape bank sites.

## Distribution status

Release bundles are currently **ad-hoc signed and not notarized**. Hardened runtime,
Developer ID signing and notarization are Phase 4. Two things to settle then: entitlements
for the PyInstaller sidecar, and Keychain access for a signed identity (an unsigned or
re-signed binary may trigger a macOS Keychain prompt when reading a key created by a
different binary).
