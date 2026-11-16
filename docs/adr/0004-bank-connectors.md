# ADR 0004: Provider-neutral bank connectors, Plaid limited to Sandbox

**Status:** accepted

**Context.** Users want transactions without exporting CSVs. Every aggregator sees the
user's data, needs long-lived credentials and has its own API shape, limits and rules.

**Decision.**

- Connectors implement one small protocol and return provider-neutral batches. One function
  applies a batch to the database, keyed by `sha256(connection id, external id)`.
- Credentials are stored only in the macOS Keychain, one item per connection.
- Each connector declares its HTTPS hosts; every URL is checked, redirects are not followed.
- SimpleFIN is supported for real use: the user creates the token, access is read-only, and
  no developer-held secret is involved.
- Plaid is supported for its Sandbox only, using `/sandbox/public_token/create` so that no
  Link script runs in the webview. The host is a constant.

**Alternatives considered.**

- *Plaid Link in the webview:* requires relaxing the content security policy to load a
  third-party script, and still leaves the production compliance question open.
- *A developer-run token server:* contradicts the project's no-cloud-backend goal.
- *Screen scraping:* rejected outright.

**Consequences.** Real-bank coverage depends on SimpleFIN. Plaid production stays out until
Plaid confirms a bring-your-own-keys desktop model is acceptable. Sync is manual for now.
