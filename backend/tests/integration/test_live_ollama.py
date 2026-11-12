"""Runs against a real local model. Skipped automatically when Ollama is not available.

    LOCALLEDGER_TEST_MODEL=llama3.2:3b uv run pytest -m live_ollama
"""

import os

import pytest

from localledger.agent.loop import ChatTurn, run_agent
from localledger.llm.base import LLMError
from localledger.llm.ollama import OllamaProvider
from tests.conftest import TODAY

MODEL = os.environ.get("LOCALLEDGER_TEST_MODEL", "llama3.2:3b")


@pytest.fixture(scope="module")
def live_provider():
    provider = OllamaProvider(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    try:
        provider.health()
        installed = {m.name for m in provider.list_models()}
    except LLMError:
        pytest.skip("Ollama is not running")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed")
    return provider


@pytest.mark.live_ollama
def test_live_model_answers_restaurant_question_from_tool(live_provider, conn, dataset):
    golden = dataset.golden["restaurants_last_month_minor"]
    result = run_agent(
        live_provider, MODEL,
        [ChatTurn(role="user", content="How much did I spend on restaurants last month?")],
        conn, TODAY,
    )
    print(result.model_dump_json(indent=1))
    good = [t for t in result.tool_calls if t.ok and t.name == "get_spending_by_category"
            and t.result.get("total_spending_minor") == golden]
    assert good, "model did not obtain the correct figure from the tool"
    assert good[0].result["period"]["start_date"] == "2026-10-01"
    assert f"{golden // 100:,}.{golden % 100:02d}" in result.reply.replace("$", "")
    assert result.grounded
