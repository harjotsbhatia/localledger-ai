/** Amounts cross the API as integer minor units; formatting never does float math on money. */
export function formatMoney(minor: number, currency = "USD", opts: { sign?: boolean } = {}) {
  const negative = minor < 0;
  const abs = Math.abs(minor);
  const whole = Math.trunc(abs / 100);
  const cents = String(abs % 100).padStart(2, "0");
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "€" : currency === "GBP" ? "£" : "";
  const body = `${symbol}${whole.toLocaleString("en-US")}.${cents}${symbol ? "" : ` ${currency}`}`;
  if (negative) return `-${body}`;
  return opts.sign && minor > 0 ? `+${body}` : body;
}

export function formatCompact(minor: number, currency = "USD") {
  const dollars = Math.round(minor / 100);
  const symbol = currency === "USD" ? "$" : "";
  const abs = Math.abs(dollars);
  const text = abs >= 1000 ? `${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k` : String(abs);
  return `${dollars < 0 ? "-" : ""}${symbol}${text}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-03" -> "Oct 3, 2026" without timezone conversion. */
export function formatDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** "2026-10" -> "Oct 26" */
export function formatMonth(month: string) {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return `${MONTHS[m - 1]} ${String(y).slice(2)}`;
}

export function formatBytes(bytes: number | null | undefined) {
  if (!bytes) return "";
  const gb = bytes / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

export const PERIODS: { value: string; label: string }[] = [
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "last_90_days", label: "Last 90 days" },
  { value: "last_6_months", label: "Last 6 months" },
  { value: "this_year", label: "This year" },
  { value: "last_12_months", label: "Last 12 months" },
  { value: "all_time", label: "All time" },
];
