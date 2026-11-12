import { formatCompact, formatDate, formatMoney, formatMonth } from "../lib/format";

describe("formatMoney", () => {
  it("renders minor units exactly", () => {
    expect(formatMoney(41237)).toBe("$412.37");
    expect(formatMoney(-5)).toBe("-$0.05");
    expect(formatMoney(123456789)).toBe("$1,234,567.89");
    expect(formatMoney(0)).toBe("$0.00");
    expect(formatMoney(115)).toBe("$1.15");
  });
  it("supports explicit sign and other currencies", () => {
    expect(formatMoney(2500, "USD", { sign: true })).toBe("+$25.00");
    expect(formatMoney(-2500, "USD", { sign: true })).toBe("-$25.00");
    expect(formatMoney(1000, "CHF")).toBe("10.00 CHF");
  });
});

describe("dates", () => {
  it("formats without timezone shifts", () => {
    expect(formatDate("2026-10-01")).toBe("Oct 1, 2026");
    expect(formatMonth("2026-10")).toBe("Oct 26");
    expect(formatCompact(650000)).toBe("$6.5k");
  });
});
