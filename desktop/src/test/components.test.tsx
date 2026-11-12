import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CategoryBars } from "../components/charts";
import { mappingProblem } from "../components/ImportFlow";

describe("CategoryBars", () => {
  const categories = [
    { category: "Housing", total_minor: 185000, transaction_count: 1, share_pct: 74 },
    { category: "Restaurants", total_minor: 65000, transaction_count: 14, share_pct: 26 },
    { category: "Shopping", total_minor: -2000, transaction_count: 1, share_pct: 0 },
  ];

  it("labels every bar with its exact value and scales widths to the data", async () => {
    const onSelect = vi.fn();
    render(<CategoryBars categories={categories} currency="USD" onSelect={onSelect} />);
    expect(screen.getByText("$1,850.00")).toBeInTheDocument();
    expect(screen.getByText("$650.00")).toBeInTheDocument();
    expect(screen.queryByText("Shopping")).not.toBeInTheDocument(); // net refund, not spending
    const bars = document.querySelectorAll<HTMLElement>(".bg-series-1");
    expect(bars[0]!.style.width).toBe("100%");
    expect(parseFloat(bars[1]!.style.width)).toBeCloseTo(35.135, 2);
    await userEvent.click(screen.getByText("Restaurants"));
    expect(onSelect).toHaveBeenCalledWith("Restaurants");
  });

  it("shows an empty state instead of an empty chart", () => {
    render(<CategoryBars categories={[]} currency="USD" />);
    expect(screen.getByText("No spending in this period.")).toBeInTheDocument();
  });
});

describe("mappingProblem", () => {
  const base = { date: "Date", description: "Description", date_format: "YYYY-MM-DD", amount_convention: "negative_is_outflow" as const };
  it("requires date, description and some amount source", () => {
    expect(mappingProblem({ ...base, date: "" })).toMatch(/date/);
    expect(mappingProblem({ ...base, description: "" })).toMatch(/description/);
    expect(mappingProblem(base)).toMatch(/amount/);
    expect(mappingProblem({ ...base, amount: "Amount" })).toBeNull();
    expect(mappingProblem({ ...base, debit: "Debit" })).toBeNull();
  });
});
