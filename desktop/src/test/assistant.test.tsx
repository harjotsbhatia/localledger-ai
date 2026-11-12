import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, type S } from "../api/client";
import { StoreProvider } from "../lib/store";
import { Assistant, keyFigures } from "../screens/Assistant";

vi.mock("../api/hooks", async (original) => ({
  ...(await original<typeof import("../api/hooks")>()),
  useSettings: () => ({ data: { model: "llama3.2:3b" } }),
}));

function result(overrides: Partial<S["AgentResult"]> = {}): S["AgentResult"] {
  return {
    reply: "You spent $412.37 on restaurants last month.",
    tool_calls: [
      {
        name: "get_spending_by_category",
        arguments: { period: "last_month", category: "Restaurants" },
        ok: true,
        duration_ms: 2,
        result: {
          period: { label: "last month", start_date: "2026-10-01", end_date: "2026-10-31" },
          category: "Restaurants",
          total_spending_minor: 41237,
          transaction_count: 14,
        },
      },
    ],
    grounded: true,
    unverified_figures: [],
    status: "ok",
    model: "llama3.2:3b",
    rounds: 2,
    llm_duration_ms: 5000,
    total_duration_ms: 5100,
    prompt_tokens: 1,
    completion_tokens: 1,
    ...overrides,
  };
}

function renderAssistant(ask: (messages: S["ChatTurn"][]) => Promise<S["AgentResult"]>) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StoreProvider ask={ask}>
        <Assistant />
      </StoreProvider>
    </QueryClientProvider>,
  );
}

describe("Assistant", () => {
  it("sends the question and shows the reply with the verified tool figure", async () => {
    const ask = vi.fn().mockResolvedValue(result());
    renderAssistant(ask);
    await userEvent.type(screen.getByLabelText("Message"), "How much did I spend on restaurants last month?{Enter}");
    expect(await screen.findByText("You spent $412.37 on restaurants last month.")).toBeInTheDocument();
    expect(ask).toHaveBeenCalledWith([{ role: "user", content: "How much did I spend on restaurants last month?" }]);
    expect(screen.getByText("Calculated spending by category")).toBeInTheDocument();
    expect(screen.getByText("$412.37")).toBeInTheDocument();
    expect(screen.getByText("2026-10-01 to 2026-10-31")).toBeInTheDocument();
    expect(screen.getByText(/Figures match the calculations/)).toBeInTheDocument();
  });

  it("warns when the model states a figure the tools did not produce", async () => {
    const ask = vi
      .fn()
      .mockResolvedValue(result({ reply: "You spent $999.00.", grounded: false, unverified_figures: ["$999.00"] }));
    renderAssistant(ask);
    await userEvent.click(screen.getByText("What are my recurring subscriptions?"));
    expect(await screen.findByText(/Unverified figures: \$999.00/)).toBeInTheDocument();
    expect(screen.getByText(/Trust the figures in the lookups below/)).toBeInTheDocument();
    expect(screen.getByText("$412.37")).toBeInTheDocument();
  });

  it("explains how to recover when the local model is unavailable", async () => {
    const ask = vi.fn().mockRejectedValue(new ApiError(503, "llm_unavailable", "Ollama is not reachable. Is it running?"));
    renderAssistant(ask);
    await userEvent.type(screen.getByLabelText("Message"), "hello{Enter}");
    expect(await screen.findByText("Ollama is not reachable. Is it running?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open AI settings" })).toBeInTheDocument();
  });

  it("extracts headline figures, including compared periods", () => {
    expect(
      keyFigures({
        difference_a_minus_b_minor: -1500,
        period_a: { total_spending_minor: 10000, label: "x" },
        note: "n",
      }),
    ).toEqual([
      { label: "difference a minus b", value: "-$15.00" },
      { label: "period a total spending", value: "$100.00" },
    ]);
  });
});
