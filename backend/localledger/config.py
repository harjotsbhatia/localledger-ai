"""Runtime configuration. Everything is local; nothing here points at a cloud service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_ID = "ai.localledger.app"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEV_ORIGINS = ("http://localhost:1420", "http://127.0.0.1:1420")
TAURI_ORIGINS = ("tauri://localhost", "http://tauri.localhost")


def is_dev() -> bool:
    return (os.environ.get("LOCALLEDGER_DEV") or "").strip().lower() in {"1", "true", "yes"}


def app_namespace() -> str:
    """Development runs use their own data folder and Keychain item, so running from source
    never touches (or triggers Keychain prompts for) the installed app's real data."""
    return f"{APP_ID}.dev" if is_dev() else APP_ID


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / app_namespace()


@dataclass(frozen=True)
class Config:
    data_dir: Path
    api_token: str
    port: int = 0
    insecure_dev_db: bool = False
    allowed_origins: tuple[str, ...] = field(default=TAURI_ORIGINS)

    @property
    def db_path(self) -> Path:
        name = "ledger.dev-unencrypted.sqlite" if self.insecure_dev_db else "ledger.db"
        return self.data_dir / name


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def load_config(api_token: str) -> Config:
    origins = TAURI_ORIGINS
    if is_dev():
        origins = TAURI_ORIGINS + DEV_ORIGINS
    data_dir = os.environ.get("LOCALLEDGER_DATA_DIR")
    return Config(
        data_dir=Path(data_dir) if data_dir else default_data_dir(),
        api_token=api_token,
        port=int(os.environ.get("LOCALLEDGER_PORT", "0")),
        insecure_dev_db=_truthy(os.environ.get("LOCALLEDGER_INSECURE_DEV_DB")),
        allowed_origins=origins,
    )
