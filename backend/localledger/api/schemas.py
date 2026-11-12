"""Typed API contract. The frontend's TypeScript types are generated from these models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from localledger.agent.loop import ChatTurn
from localledger.ingestion.csv_parser import ColumnMapping


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    storage_encrypted: bool
    storage_mode: Literal["sqlcipher", "insecure-dev-plaintext"]
    today: str


class Account(BaseModel):
    id: int
    name: str
    institution: str
    type: str
    currency: str
    connector: str
    transaction_count: int
    first_date: str | None
    last_date: str | None
    net_flow_minor: int


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    institution: str = Field("", max_length=80)
    type: Literal["checking", "savings", "credit_card", "other"] = "checking"
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")


class PreviewRequest(BaseModel):
    content: str


class ImportRequest(BaseModel):
    account_id: int
    filename: str = Field(max_length=255)
    content: str
    mapping: ColumnMapping


class Transaction(BaseModel):
    id: int
    posted_date: str
    amount_minor: int
    currency: str
    description_raw: str
    merchant: str
    category: str
    is_pending: bool
    is_transfer: bool
    account_id: int
    account_name: str


class TransactionPage(BaseModel):
    total_count: int
    net_amount_minor: int
    transactions: list[Transaction]


class PeriodInfo(BaseModel):
    label: str
    start_date: str
    end_date: str


class CashFlow(BaseModel):
    income_minor: int
    spending_minor: int
    net_cash_flow_minor: int
    savings_rate_pct: float | None
    transaction_count: int
    pending_count: int


class CategoryTotal(BaseModel):
    category: str
    total_minor: int
    transaction_count: int
    share_pct: float


class MerchantTotal(BaseModel):
    merchant: str
    category: str
    total_minor: int
    transaction_count: int


class MonthPoint(BaseModel):
    month: str
    income_minor: int
    spending_minor: int
    net_cash_flow_minor: int


class Overview(BaseModel):
    period: PeriodInfo
    currency: str
    has_data: bool
    cash_flow: CashFlow
    categories: list[CategoryTotal]
    top_merchants: list[MerchantTotal]
    trend: list[MonthPoint]


class Recurring(BaseModel):
    merchant: str
    category: str
    cadence: str
    typical_amount_minor: int
    amount_varies: bool
    occurrences: int
    last_date: str
    next_expected_date: str
    estimated_annual_cost_minor: int


class Settings(BaseModel):
    ollama_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    offline_mode: bool = False
    onboarding_complete: bool = False


class SettingsUpdate(BaseModel):
    ollama_url: str | None = None
    model: str | None = None
    offline_mode: bool | None = None
    onboarding_complete: bool | None = None


class OllamaModel(BaseModel):
    name: str
    size_bytes: int | None
    parameter_size: str | None


class OllamaStatus(BaseModel):
    reachable: bool
    version: str | None
    url: str
    models: list[OllamaModel]
    selected_model: str | None
    selected_model_installed: bool


class PullRequest(BaseModel):
    model: str = Field(pattern=r"^[A-Za-z0-9._\-/]+(:[A-Za-z0-9._\-]+)?$", max_length=120)


class PullStatus(BaseModel):
    model: str | None
    state: Literal["idle", "running", "done", "error"]
    detail: str
    completed_bytes: int
    total_bytes: int


class ChatRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)


class DeleteRequest(BaseModel):
    confirm: Literal["DELETE"]


class DemoResult(BaseModel):
    accounts: int
    rows_inserted: int
    rows_duplicate: int


class ErrorDetail(BaseModel):
    code: str
    message: str
