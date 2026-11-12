import { useEffect, useState } from "react";
import { useAccounts, useCategories, useTransactions } from "../api/hooks";
import { Badge, Button, Card, Input, PageHeader, Select } from "../components/ui";
import { formatDate, formatMoney, PERIODS } from "../lib/format";
import { useStore } from "../lib/store";

const PAGE = 50;

export function Transactions() {
  const { txCategory, setTxCategory } = useStore();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [period, setPeriod] = useState("");
  const [account, setAccount] = useState("");
  const [offset, setOffset] = useState(0);
  const categories = useCategories();
  const accounts = useAccounts();

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    setOffset(0);
  }, [debounced, period, account, txCategory]);

  const page = useTransactions({
    query: debounced || undefined,
    category: txCategory || undefined,
    period: period || undefined,
    account_id: account ? Number(account) : undefined,
    limit: PAGE,
    offset,
  });
  const data = page.data;

  return (
    <div>
      <PageHeader
        title="Transactions"
        subtitle={
          data
            ? `${data.total_count.toLocaleString()} matching · net ${formatMoney(data.net_amount_minor, "USD", { sign: true })}`
            : undefined
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input
          type="search"
          placeholder="Search merchant or description"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-72"
          aria-label="Search transactions"
        />
        <Select aria-label="Category" value={txCategory} onChange={(e) => setTxCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.data?.map((c) => <option key={c}>{c}</option>)}
        </Select>
        <Select aria-label="Account" value={account} onChange={(e) => setAccount(e.target.value)}>
          <option value="">All accounts</option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="">Any date</option>
          {PERIODS.filter((p) => p.value !== "all_time").map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </Select>
      </div>
      <Card className="p-0">
        <table className="w-full text-left text-[13px]">
          <thead className="text-xs text-ink-2">
            <tr className="border-b border-line">
              <th className="px-5 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Merchant</th>
              <th className="px-3 py-3 font-medium">Category</th>
              <th className="px-3 py-3 font-medium">Account</th>
              <th className="px-5 py-3 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {data?.transactions.map((t) => (
              <tr key={t.id} className="border-b border-line last:border-0 hover:bg-surface-2" title={t.description_raw}>
                <td className="tnum whitespace-nowrap px-5 py-2.5 text-ink-2">{formatDate(t.posted_date)}</td>
                <td className="max-w-80 truncate px-3 py-2.5 text-ink">
                  {t.merchant}
                  {t.is_pending && (
                    <span className="ml-2">
                      <Badge tone="warning">Pending</Badge>
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <Badge>{t.category}</Badge>
                </td>
                <td className="px-3 py-2.5 text-ink-2">{t.account_name}</td>
                <td className="tnum whitespace-nowrap px-5 py-2.5 text-right text-ink">
                  {formatMoney(t.amount_minor, t.currency, { sign: true })}
                </td>
              </tr>
            ))}
            {data && data.transactions.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-ink-3">
                  No transactions match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
      {data && data.total_count > PAGE && (
        <div className="mt-3 flex items-center justify-end gap-3 text-xs text-ink-2">
          <span className="tnum">
            {offset + 1}–{Math.min(offset + PAGE, data.total_count)} of {data.total_count.toLocaleString()}
          </span>
          <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </Button>
          <Button size="sm" disabled={offset + PAGE >= data.total_count} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
