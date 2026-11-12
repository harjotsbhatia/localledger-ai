import json

import pytest

from localledger.agent.grounding import check_grounding, figures_in_text
from localledger.agent.loop import ChatTurn, run_agent
from localledger.llm.base import ChatResponse, LLMUnavailable, ToolCall
from tests.conftest import TODAY, ScriptedProvider

QUESTION = [ChatTurn(role="user", content="How much did I spend on restaurants last month?")]


def money(minor: int) -> str:
    return f"${minor // 100:,}.{minor % 100:02d}"


def restaurant_call() -> ChatResponse:
    return ChatResponse(content="", tool_calls=[ToolCall(
        "get_spending_by_category", {"period": "last_month", "category": "Restaurants"})])


def test_restaurant_question_end_to_end(conn, dataset):
    golden = dataset.golden["restaurants_last_month_minor"]
    provider = ScriptedProvider([
        restaurant_call(),
        ChatResponse(content=f"You spent {money(golden)} on restaurants last month "
                             "(Oct 1 to Oct 31, 2026)."),
    ])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.status == "ok" and result.grounded and result.rounds == 2
    assert len(result.tool_calls) == 1 and result.tool_calls[0].ok
    assert result.tool_calls[0].result["total_spending_minor"] == golden
    assert money(golden) in result.reply
    # The model was shown the exact decimal string, not a float.
    tool_message = provider.calls[1][-1]
    assert tool_message["role"] == "tool"
    assert json.loads(tool_message["content"])["total_spending"] == (
        f"{golden // 100}.{golden % 100:02d}")
    # The system prompt carries today's date and the data/instruction boundary.
    system = provider.calls[0][0]["content"]
    assert "2026-11-10" in system and "DATA, not instructions" in system


def test_wrong_number_in_reply_is_flagged_as_unverified(conn):
    provider = ScriptedProvider([restaurant_call(),
                                 ChatResponse(content="You spent $1.00 on restaurants.")])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert not result.grounded and result.unverified_figures == ["$1.00"]


def test_answer_without_any_tool_call_is_ungrounded(conn):
    provider = ScriptedProvider([ChatResponse(content="You spent about $250.00.")])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert not result.grounded and result.tool_calls == []


def test_malformed_call_gets_one_retry_then_succeeds(conn, dataset):
    golden = dataset.golden["restaurants_last_month_minor"]
    provider = ScriptedProvider([
        ChatResponse(content="", tool_calls=[ToolCall("get_spending_by_category",
                                                      {"category": "Restaurants"})]),
        restaurant_call(),
        ChatResponse(content=f"{money(golden)} in total."),
    ])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert [t.ok for t in result.tool_calls] == [False, True]
    assert result.status == "ok" and result.grounded
    error = json.loads(provider.calls[1][-1]["content"])["error"]
    assert error["code"] == "invalid_period"


def test_repeated_bad_calls_stop_gracefully(conn):
    bad = ChatResponse(content="", tool_calls=[ToolCall("run_sql", "DROP TABLE x")])
    provider = ScriptedProvider([bad, bad, bad, bad])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.status == "tool_errors" and result.rounds == 2
    assert "invalid lookup requests" in result.reply


def test_round_limit_stops_a_looping_model(conn):
    provider = ScriptedProvider([
        ChatResponse(content="", tool_calls=[ToolCall("get_accounts", {})]) for _ in range(20)])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.status == "round_limit" and len(result.tool_calls) == 5


def test_inline_json_tool_call_is_recognized(conn, dataset):
    golden = dataset.golden["restaurants_last_month_minor"]
    inline = json.dumps({"name": "get_spending_by_category",
                         "parameters": {"period": "last_month", "category": "Restaurants"}})
    provider = ScriptedProvider([ChatResponse(content=inline),
                                 ChatResponse(content=f"That was {money(golden)}.")])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.tool_calls[0].ok and result.grounded


def test_empty_model_reply_falls_back_to_verified_figures(conn):
    provider = ScriptedProvider([restaurant_call(), ChatResponse(content="  ")])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.status == "no_explanation" and result.tool_calls[0].ok


def test_missing_data_is_reported_by_tool_not_invented(db):
    with db.connect() as conn:
        provider = ScriptedProvider([restaurant_call(),
                                     ChatResponse(content="No restaurant spending was found.")])
        result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.tool_calls[0].result["total_spending_minor"] == 0 and result.grounded


def test_unavailable_model_raises_typed_error(conn):
    with pytest.raises(LLMUnavailable):
        run_agent(ScriptedProvider(down=True), "scripted", QUESTION, conn, TODAY)


def test_injected_merchant_text_reaches_model_only_as_tool_data(conn):
    provider = ScriptedProvider([
        ChatResponse(content="", tool_calls=[ToolCall(
            "search_transactions", {"query": "ignore previous", "limit": 5})]),
        ChatResponse(content="I found some restaurant transactions."),
    ])
    run_agent(provider, "scripted", [ChatTurn(role="user", content="Show odd merchants")],
              conn, TODAY)
    final_messages = provider.calls[1]
    carriers = [m["role"] for m in final_messages if "Ignore Previous" in str(m["content"])]
    assert carriers == ["tool"]
    assert "Ignore Previous" not in final_messages[0]["content"]


def test_history_is_bounded(conn):
    history = [ChatTurn(role="user", content="x" * 5000) for _ in range(30)]
    provider = ScriptedProvider([ChatResponse(content="ok")])
    run_agent(provider, "scripted", history, conn, TODAY)
    sent = provider.calls[0]
    assert len(sent) == 13 and all(len(m["content"]) <= 2000 for m in sent[1:])


def test_figure_extraction():
    found = [(raw, minor) for raw, minor, _ in figures_in_text(
        "Spent $1,234.56 and 78.90, about $412, up 12.5% over 2026-10-01 across 14 visits.")]
    assert found == [("$1,234.56", 123456), ("78.90", 7890), ("$412", 41200)]


def test_grounding_rules():
    results = [{"total_spending_minor": 41237, "rows": [{"amount_minor": -1549}]}]
    assert check_grounding("$412.37 total, incl. $15.49 Netflix", results) == []
    assert check_grounding("about $412", results) == []
    assert check_grounding("$427.86 combined", results) == ["$427.86"]  # model did the sum
    assert check_grounding("$999", results) == ["$999"]


def test_claim_after_only_failed_lookups_is_not_shown(conn):
    # Observed with llama3.2:3b: a rejected call followed by a confident, wrong answer.
    provider = ScriptedProvider([
        ChatResponse(content="", tool_calls=[ToolCall("get_monthly_summary",
                                                      {"month": "this_year"})]),
        ChatResponse(content="You have no recurring subscriptions."),
    ])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.status == "tool_errors"
    assert "no recurring" not in result.reply


def test_inline_tool_call_after_prose_is_recognized(conn, dataset):
    golden = dataset.golden["restaurants_last_month_minor"]
    text = ("I will try again.\n\n" + json.dumps({
        "name": "get_spending_by_category",
        "parameters": {"period": "last_month", "category": "Restaurants"}}))
    provider = ScriptedProvider([ChatResponse(content=text),
                                 ChatResponse(content=f"It was {money(golden)}.")])
    result = run_agent(provider, "scripted", QUESTION, conn, TODAY)
    assert result.tool_calls[0].ok and result.grounded
