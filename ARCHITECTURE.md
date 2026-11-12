# Architecture

```
┌──────────────────────────── LocalLedger.app ────────────────────────────┐
│  Tauri 2 shell (Rust)                                                    │
│   • picks a free loopback port, mints a 256-bit token per launch         │
│   • starts the sidecar, passes the token over stdin                      │
│   • native file picker (path never reaches JavaScript)                   │
│        │ IPC: get_backend_info, pick_statement_file                      │
│  React + TypeScript UI (webview, strict CSP)                             │
│        │ HTTP on 127.0.0.1 + Authorization: Bearer <token>               │
│  Python sidecar (FastAPI)                                                │
│   api/         routes, typed schemas (OpenAPI → TypeScript)              │
│   security/    Host + token guard, keychain, logging policy              │
│   ingestion/   CSV parsing, mapping, normalization, categorization, dedup│
│   connectors/  Connector protocol (CSV today; Plaid/SimpleFIN later)     │
│   analytics/   deterministic calculations, period resolution             │
│   agent/       tool registry, tool-calling loop, grounding check         │
│   llm/         LLMProvider protocol → OllamaProvider                     │
│   storage/     SQLCipher database, migrations                            │
│   demo/        seeded synthetic data generator                           │
└──────────────────────────────────────────────────────────────────────────┘
        │ loopback only                         │
   Ollama (127.0.0.1:11434)              macOS Keychain (database key)
```

There is no developer-operated server. The only network peers are Ollama on loopback and,
when the user explicitly downloads a model, Ollama's own registry.

## Layers and their contracts

| Layer | Knows about | Does not know about |
|---|---|---|
| UI | generated API types | SQL, Ollama, files |
| API | schemas, analytics, agent | how a provider talks to a model |
| Agent | tool registry, `LLMProvider` | HTTP, FastAPI |
| Analytics | normalized `transactions` rows | where rows came from |
| Connectors | their source format | analytics, AI |

Adding a bank provider means implementing `connectors.base.Connector` and writing normalized
rows. Analytics and the assistant do not change.

## Data conventions

- **Money** is stored as integer minor units (`amount_minor`) with a currency code. Parsing
  uses `Decimal`; floats are never used for money. Negative means money out.
- **Transfers** between own accounts, including credit-card payments, are flagged and excluded
  from income and spending.
- **Spending** in a category is net of refunds. **Income** is the Income category.
  Net cash flow = income − spending. Pending transactions are included and counted.
- **Deduplication** uses `sha256(account, date, amount, normalized description, n)` where `n`
  is the row's occurrence index among identical rows in the file. Re-imports and overlapping
  statements collide; two genuine identical purchases on one day both survive. Pending status
  is excluded from the fingerprint so a pending row settles in place.
- **Categorization** is ordered keyword rules. It is deterministic by design.
- One currency is assumed for aggregated totals (Phase 1 limitation).

## Assistant request flow

1. UI posts the conversation to `POST /api/chat`.
2. `agent.loop.run_agent` builds a system prompt containing today's date and the rule that
   tool results are data, then calls the provider with the seven tool schemas.
3. The model returns tool calls. Each is validated by a Pydantic model
   (`agent.tools`): unknown tools, malformed JSON and bad arguments become structured errors
   returned to the model. Named periods (`last_month`) are resolved by the server; if a named
   period is present, any dates the model also sent are ignored.
4. Tool handlers call `analytics.core`, which runs static, parameterized, read-only SQL.
5. Results go back to the model with amounts rendered as exact decimal strings.
6. The loop ends on a text reply, after 5 rounds, or after two consecutive rounds of failed
   calls. If every call failed, the model's text is discarded.
7. `agent.grounding` extracts monetary figures from the reply and flags any that no tool
   produced. The UI shows the reply, the verdict, and every lookup with its date range.

## Local API security

See `SECURITY.md`. In short: bind `127.0.0.1` only, random port, bearer token on every route,
Host header allow-list, CORS limited to the app origin, no cookies, docs endpoints disabled.

## Typed contract

`pnpm gen:api` exports the FastAPI OpenAPI document and generates `desktop/src/api/schema.ts`.
CI regenerates both and fails if they differ from what is committed.

## What has been verified, and how

| Claim | Evidence |
|---|---|
| Calculations are correct | Golden answers computed independently by the data generator; compared for every month and category |
| Database is encrypted at rest | Test reads the raw file bytes and tries the stock SQLite driver |
| API rejects other callers | Tests for missing/wrong token, rebinding hosts, foreign origins |
| Desktop shell starts and reaches the sidecar | Dev build and release bundle launched; sidecar request log showed the webview's calls |
| Real model answers the milestone question | `tests/integration/test_live_ollama.py`, and by hand in the UI |
| UI screens render with real data | Driven in a browser against the real backend (dark and light) |

Not verified by automation: the native open panel and window dragging (they need a human at
the screen), and behavior on Intel Macs.
