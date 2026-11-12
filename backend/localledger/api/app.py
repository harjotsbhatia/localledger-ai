"""FastAPI application factory for the local sidecar."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from starlette.middleware.cors import CORSMiddleware

from localledger import __version__
from localledger.agent.loop import AgentResult, run_agent
from localledger.analytics import core
from localledger.analytics.periods import PeriodError, resolve_period, resolve_range
from localledger.api import schemas as s
from localledger.config import Config
from localledger.demo.loader import load_demo
from localledger.ingestion.categorize import CATEGORIES
from localledger.ingestion.csv_parser import CsvError, CsvPreview, preview
from localledger.ingestion.importer import ImportResult, import_csv
from localledger.llm.base import LLMError, LLMProvider
from localledger.llm.ollama import OllamaProvider, validate_local_url
from localledger.security.http import LocalApiGuard
from localledger.storage.db import Database

ProviderFactory = Callable[[str], LLMProvider]
log = logging.getLogger(__name__)


class DevRequestLog:
    """Development aid: logs method, path, origin and status. Never query strings or bodies."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = dict(scope.get("headers", [])).get(b"origin", b"-").decode("latin-1")

        async def wrapped(message: Any) -> None:
            if message["type"] == "http.response.start":
                log.info("%s %s origin=%s -> %s", scope["method"], scope["path"], origin,
                         message["status"])
            await send(message)

        await self.app(scope, receive, wrapped)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def create_app(
    config: Config,
    db: Database,
    *,
    clock: Callable[[], date] = date.today,
    provider_factory: ProviderFactory = OllamaProvider,
    log_requests: bool = False,
) -> FastAPI:
    app = FastAPI(title="LocalLedger local API", version=__version__,
                  docs_url=None, redoc_url=None, openapi_url=None)
    # Order matters: CORS is outermost so that rejections still carry CORS headers for the
    # app's own origin; the guard then enforces Host + bearer token on everything.
    app.add_middleware(LocalApiGuard, token=config.api_token)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(config.allowed_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"], max_age=600,
    )
    if log_requests:
        app.add_middleware(DevRequestLog)  # outermost: also sees rejected requests

    pull_state: dict[str, Any] = {"model": None, "state": "idle", "detail": "",
                                  "completed_bytes": 0, "total_bytes": 0}
    pull_lock = threading.Lock()

    def conn_dep() -> Iterator[Any]:
        with db.connect() as conn:
            yield conn

    def read_settings(conn: Any) -> s.Settings:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return s.Settings(**{r["key"]: json.loads(r["value"]) for r in rows
                             if r["key"] in s.Settings.model_fields})

    def period_or_400(period: str | None, start: date | None, end: date | None):
        try:
            return resolve_range(period, start, end, clock())
        except PeriodError as exc:
            raise _error(400, "invalid_period", str(exc)) from exc

    def category_or_400(category: str | None) -> str | None:
        if category is not None and category not in CATEGORIES:
            raise _error(400, "unknown_category", "Unknown category.")
        return category

    @app.get("/api/health", response_model=s.Health)
    def health() -> s.Health:
        return s.Health(
            status="ok", version=__version__, storage_encrypted=db.encrypted,
            storage_mode="sqlcipher" if db.encrypted else "insecure-dev-plaintext",
            today=clock().isoformat(),
        )

    # ---- accounts -------------------------------------------------------------------
    @app.get("/api/accounts", response_model=list[s.Account])
    def list_accounts(conn: Any = Depends(conn_dep)) -> Any:
        return core.accounts_summary(conn)

    @app.post("/api/accounts", response_model=s.Account, status_code=201)
    def create_account(body: s.AccountCreate, conn: Any = Depends(conn_dep)) -> Any:
        name = body.name.strip()
        if conn.execute("SELECT 1 FROM accounts WHERE name = ?", (name,)).fetchone():
            raise _error(409, "account_exists", "An account with that name already exists.")
        cursor = conn.execute(
            "INSERT INTO accounts (name, institution, type, currency) VALUES (?, ?, ?, ?)",
            (name, body.institution.strip(), body.type, body.currency),
        )
        return next(a for a in core.accounts_summary(conn) if a["id"] == cursor.lastrowid)

    @app.delete("/api/accounts/{account_id}", status_code=204)
    def delete_account(account_id: int, conn: Any = Depends(conn_dep)) -> None:
        deleted = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,)).rowcount
        if not deleted:
            raise _error(404, "not_found", "Account not found.")

    # ---- imports --------------------------------------------------------------------
    @app.post("/api/imports/preview", response_model=CsvPreview)
    def import_preview(body: s.PreviewRequest) -> CsvPreview:
        try:
            return preview(body.content)
        except CsvError as exc:
            raise _error(400, "invalid_csv", str(exc)) from exc

    @app.post("/api/imports", response_model=ImportResult)
    def run_import(body: s.ImportRequest, conn: Any = Depends(conn_dep)) -> ImportResult:
        try:
            return import_csv(conn, account_id=body.account_id, filename=body.filename,
                              content=body.content, mapping=body.mapping)
        except LookupError as exc:
            raise _error(404, "not_found", str(exc)) from exc
        except (CsvError, ValueError) as exc:
            raise _error(400, "invalid_csv", str(exc)) from exc

    @app.post("/api/demo/load", response_model=s.DemoResult)
    def demo_load(conn: Any = Depends(conn_dep)) -> s.DemoResult:
        """Loads clearly-labelled synthetic data, generated relative to today."""
        results = load_demo(conn, clock())
        return s.DemoResult(accounts=len(results),
                            rows_inserted=sum(r.rows_inserted for r in results),
                            rows_duplicate=sum(r.rows_duplicate for r in results))

    # ---- transactions & analytics ---------------------------------------------------
    @app.get("/api/categories", response_model=list[str])
    def categories() -> list[str]:
        return list(CATEGORIES)

    @app.get("/api/transactions", response_model=s.TransactionPage)
    def transactions(
        query: str | None = Query(None, max_length=80),
        category: str | None = None,
        account_id: int | None = None,
        period: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        conn: Any = Depends(conn_dep),
    ) -> Any:
        rng = period_or_400(period, start_date, end_date) if (
            period or start_date or end_date) else None
        return core.search_transactions(
            conn, rng=rng, query=query or None, category=category_or_400(category),
            account_id=account_id, limit=limit, offset=offset,
        )

    @app.get("/api/analytics/overview", response_model=s.Overview)
    def overview(period: str = "this_month", conn: Any = Depends(conn_dep)) -> Any:
        rng = period_or_400(period, None, None)
        spending = core.spending_by_category(conn, rng)
        trend_range = resolve_period("last_12_months", clock())
        trend_range = type(trend_range)(trend_range.start, clock(), "trend")
        has_data = conn.execute("SELECT 1 FROM transactions LIMIT 1").fetchone() is not None
        return {
            "period": {"label": rng.label, "start_date": rng.start.isoformat(),
                       "end_date": rng.end.isoformat()},
            "currency": core.primary_currency(conn),
            "has_data": has_data,
            "cash_flow": core.cash_flow(conn, rng),
            "categories": spending["categories"],
            "top_merchants": core.top_merchants(conn, rng, 8),
            "trend": core.monthly_trend(conn, trend_range),
        }

    @app.get("/api/analytics/recurring", response_model=list[s.Recurring])
    def recurring(conn: Any = Depends(conn_dep)) -> Any:
        return core.recurring_transactions(conn, clock(), 6)

    # ---- settings & local model -----------------------------------------------------
    @app.get("/api/settings", response_model=s.Settings)
    def get_settings(conn: Any = Depends(conn_dep)) -> s.Settings:
        return read_settings(conn)

    @app.put("/api/settings", response_model=s.Settings)
    def put_settings(body: s.SettingsUpdate, conn: Any = Depends(conn_dep)) -> s.Settings:
        updates = body.model_dump(exclude_unset=True)
        if updates.get("ollama_url") is not None:
            try:
                updates["ollama_url"] = validate_local_url(updates["ollama_url"])
            except ValueError as exc:
                raise _error(400, "invalid_url", str(exc)) from exc
        for key, value in updates.items():
            if value is None and key != "model":
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
        return read_settings(conn)

    @app.get("/api/ollama/status", response_model=s.OllamaStatus)
    def ollama_status(conn: Any = Depends(conn_dep)) -> s.OllamaStatus:
        settings = read_settings(conn)
        try:
            provider = provider_factory(settings.ollama_url)
            version = provider.health().get("version")
            models = [s.OllamaModel(name=m.name, size_bytes=m.size_bytes,
                                    parameter_size=m.parameter_size)
                      for m in provider.list_models()]
            reachable = True
        except (LLMError, ValueError):
            version, models, reachable = None, [], False
        return s.OllamaStatus(
            reachable=reachable, version=version, url=settings.ollama_url, models=models,
            selected_model=settings.model,
            selected_model_installed=any(m.name == settings.model for m in models),
        )

    @app.post("/api/ollama/pull", response_model=s.PullStatus, status_code=202)
    def ollama_pull(body: s.PullRequest, conn: Any = Depends(conn_dep)) -> Any:
        settings = read_settings(conn)
        if settings.offline_mode:
            raise _error(409, "offline_mode",
                         "Offline mode is on. Turn it off to download a model.")
        with pull_lock:
            if pull_state["state"] == "running":
                raise _error(409, "pull_in_progress", "A download is already running.")
            pull_state.update(model=body.model, state="running", detail="starting",
                              completed_bytes=0, total_bytes=0)
        provider = provider_factory(settings.ollama_url)

        def worker() -> None:
            try:
                for event in provider.pull(body.model):  # type: ignore[attr-defined]
                    if event.get("error"):
                        raise LLMError(str(event["error"])[:200])
                    pull_state.update(
                        detail=str(event.get("status", ""))[:80],
                        completed_bytes=int(event.get("completed") or 0),
                        total_bytes=int(event.get("total") or 0),
                    )
                pull_state.update(state="done", detail="success")
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI as state
                pull_state.update(state="error", detail=str(exc)[:200])

        threading.Thread(target=worker, daemon=True).start()
        return dict(pull_state)

    @app.get("/api/ollama/pull", response_model=s.PullStatus)
    def ollama_pull_status() -> Any:
        return dict(pull_state)

    # ---- assistant ------------------------------------------------------------------
    @app.post("/api/chat", response_model=AgentResult)
    def chat(body: s.ChatRequest, conn: Any = Depends(conn_dep)) -> AgentResult:
        if body.messages[-1].role != "user":
            raise _error(400, "invalid_request", "The last message must be from the user.")
        settings = read_settings(conn)
        if not settings.model:
            raise _error(409, "no_model", "Choose a local model in AI settings first.")
        try:
            provider = provider_factory(settings.ollama_url)
            return run_agent(provider, settings.model, body.messages, conn, clock(),
                             core.primary_currency(conn))
        except LLMError as exc:
            raise _error(503, exc.code, str(exc)) from exc

    # ---- privacy --------------------------------------------------------------------
    @app.post("/api/data/delete", status_code=204)
    def delete_data(body: s.DeleteRequest) -> None:
        db.delete_all_data()

    return app
