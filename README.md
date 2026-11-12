# LocalLedger AI

A privacy-first personal finance assistant for macOS. Your transactions are stored in an
encrypted database on your own Mac, and questions are answered by a language model running
locally in [Ollama](https://ollama.com). No cloud account, no telemetry.

> **Status: Phase 1 (working local MVP).** CSV import, dashboard, and the local AI assistant
> work and are tested. Bank connections (Plaid, SimpleFIN), RAG, and a signed installer are
> **not implemented yet**. See [What works and what doesn't](#what-works-and-what-doesnt).

## How it answers questions

The model never does arithmetic. It reads your question, picks one of seven read-only tools,
and ordinary code computes the answer from the database. The model then phrases the result.

```
"How much did I spend on restaurants last month?"
   → model calls get_spending_by_category(period="last_month", category="Restaurants")
   → server resolves "last_month" to exact dates and sums integer cents in SQLite
   → model: "You spent $360.14 on restaurants last month."
   → the app checks every figure in that sentence against the tool output and shows the lookup
```

If the model writes an amount the tools did not produce, the answer is flagged as unverified.

## What leaves your Mac

| Activity | Leaves the device? |
|---|---|
| CSV import, dashboard, analytics | No |
| AI questions and answers | No. Only loopback Ollama URLs are accepted |
| Downloading a model | Ollama fetches the model from its registry, only when you click Download. No financial data is sent |
| Bank connections (future) | **Yes.** Aggregators such as Plaid see your transactions. Not implemented; the app will say so before you connect |
| Analytics / telemetry | None |

## Requirements

- macOS 14 or newer (developed on Apple Silicon; Intel is untested)
- [Ollama](https://ollama.com/download) for the assistant (optional for the dashboard)
- For development: Rust (rustup), Node 22+, pnpm, [uv](https://docs.astral.sh/uv/)

```bash
brew install rustup node@22 uv ollama && npm i -g pnpm && rustup default stable
```

## Run it (development)

```bash
cd backend && uv sync
```

```bash
cd desktop && pnpm install && pnpm tauri dev
```

The desktop shell starts the Python backend itself. On first launch:

1. Walk through onboarding. Under **Local AI**, pick an installed model, or download one
   (`llama3.2:3b`, about 2 GB, is a reasonable start on an 8 GB Mac).
2. Click **Load synthetic demo data**, or import `data/synthetic/everyday_checking.csv` and
   `data/synthetic/rewards_credit_card.csv` under **Accounts**.
3. Open **Assistant** (⌘K) and ask: *How much did I spend on restaurants last month?*

Shortcuts: ⌘1–⌘7 switch sections, ⌘K focuses the assistant.

## Build the app bundle

```bash
cd backend && uv run python scripts/build_sidecar.py
```

```bash
cd desktop && pnpm tauri build --config src-tauri/tauri.bundle.conf.json
```

This produces `desktop/src-tauri/target/release/bundle/macos/LocalLedger.app` with the
backend bundled, so no Python is needed to run it. The bundle is **ad-hoc signed only**: it
runs on the machine that built it, but is not notarized and Gatekeeper will block it elsewhere.

## Tests and checks

```bash
cd backend && uv run ruff check . && uv run pytest
```

```bash
cd desktop && pnpm typecheck && pnpm lint && pnpm test
```

```bash
cd desktop/src-tauri && cargo check
```

With Ollama running, `uv run pytest -m live_ollama` asks a real model the restaurant
question and checks the figure against the golden answer.

## Model evaluation

```bash
cd backend && uv run python ../evals/run_eval.py --model llama3.2:3b
```

Runs 13 questions with known answers and writes a JSON report to `evals/reports/`. Pass
`--model` several times to compare models. A measured baseline is committed at
`evals/baselines/llama3.2-3b.json`:

| llama3.2:3b, M2 8 GB, single run, temperature 0 | Result |
|---|---|
| Cases passed | 11 / 13 |
| Tool selection | 13 / 13 |
| Tool arguments | 7 / 8 |
| Numerical accuracy | 9 / 10 |
| Figures grounded in tool output | 13 / 13 |
| Prompt-injection cases | 2 / 2 |
| Median latency | 6.1 s (max 21.0 s, includes model load) |
| Ollama peak memory | about 3.0 GB |

Treat these as a small smoke benchmark, not a general claim: 13 cases, one run, and results
varied between runs (7, 10 and 11 of 13 as server-side tolerance for malformed arguments was
added). The two failures are real model mistakes: it answered "no Netflix charges" after a
bad search, and it used the wrong year for a 2020 question while describing the answer as
2020. The grounding check verifies amounts, not dates, so always read the date range shown
on each lookup.

## What works and what doesn't

**Works and is tested**

- Tauri 2 desktop shell that starts a bundled Python (FastAPI) sidecar on a random loopback port
- SQLCipher-encrypted database, key in the macOS Keychain
- Local API protection: per-launch bearer token, Host allow-list, strict CORS
- CSV import with format detection, manual column mapping, normalization, deduplication,
  pending-to-posted settling, transfer detection, rule-based categorization
- Dashboard, transaction explorer and analytics driven by database queries
- Ollama integration behind a provider interface; seven schema-validated read-only tools
- Grounding check, tool trace in the UI, graceful handling of model and tool errors
- Offline mode, delete-account and delete-all-data
- 129 backend tests, 10 frontend tests, a live-model test, an evaluation runner

**Not implemented**

- Plaid and SimpleFIN connectors (only the connector interface exists)
- RAG over documents, forecasting, full evaluation suite and model comparison reports
- Developer ID signing, notarization, `.dmg`, Intel/universal builds, auto-update
- Multi-currency totals (one currency is assumed), European decimal commas (rejected, not guessed),
  editing categories, chat history persistence, streaming replies

**Known limitations**

- The bundled sidecar is a single-file executable and takes around 8 seconds to start cold.
- Small models make mistakes. Amounts are verified; wording and date interpretation are not.
- The native file picker and window chrome were exercised manually only in part; see
  `SECURITY.md` and `ARCHITECTURE.md` for what was verified and how.

## Troubleshooting

- **"Starting the local engine…" does not go away.** macOS may be showing a Keychain prompt
  (possibly behind other windows) asking whether `localledger-backend` may read the
  `ai.localledger.app` item. That item is the database key. Choose **Always Allow**. Unsigned
  builds are asked again after every rebuild, because each build is a new identity to macOS;
  a Developer ID signed release will not have this problem.
- **The assistant says Ollama is not reachable.** Start the Ollama app or run `ollama serve`.
- **Start over.** Privacy → Delete all data. To also discard the key:
  `security delete-generic-password -s ai.localledger.app` and delete
  `~/Library/Application Support/ai.localledger.app`. Without the key the old database
  cannot be read.

Running from source (`pnpm tauri dev`) uses a separate data folder and Keychain item
(`ai.localledger.app.dev`), so development never touches the installed app's data.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): components, data flow, conventions
- [SECURITY.md](SECURITY.md): threat model and security decisions
- [CONTRIBUTING.md](CONTRIBUTING.md): development workflow
- [docs/adr](docs/adr): architecture decision records
- [docs/ROADMAP.md](docs/ROADMAP.md): phases 2–4

## License

Apache-2.0. See [LICENSE](LICENSE).
