import { FileUp } from "lucide-react";
import { useState } from "react";
import { ApiError, pickStatement, type S, type StatementFile } from "../api/client";
import { useAccounts, useCreateAccount, useImportCsv, usePreviewCsv } from "../api/hooks";
import { Button, Card, CardTitle, Field, Input, Notice, Select } from "./ui";

type Mapping = S["ColumnMapping"];
const NONE = "";

const EMPTY: Mapping = {
  date: "",
  description: "",
  amount: null,
  debit: null,
  credit: null,
  status: null,
  date_format: "YYYY-MM-DD",
  amount_convention: "negative_is_outflow",
};

export function mappingProblem(mapping: Mapping): string | null {
  if (!mapping.date) return "Choose the date column.";
  if (!mapping.description) return "Choose the description column.";
  if (!mapping.amount && !mapping.debit && !mapping.credit)
    return "Choose an amount column, or debit and credit columns.";
  return null;
}

export function ImportFlow({ onDone }: { onDone?: () => void }) {
  const accounts = useAccounts();
  const createAccount = useCreateAccount();
  const previewCsv = usePreviewCsv();
  const importCsv = useImportCsv();

  const [accountChoice, setAccountChoice] = useState<string>("new");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<S["AccountCreate"]["type"]>("checking");
  const [file, setFile] = useState<StatementFile | null>(null);
  const [preview, setPreview] = useState<S["CsvPreview"] | null>(null);
  const [mapping, setMapping] = useState<Mapping>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<S["ImportResult"] | null>(null);

  const existing = accounts.data ?? [];
  const choice = accountChoice === "new" || existing.some((a) => String(a.id) === accountChoice) ? accountChoice : "new";

  async function chooseFile() {
    setError(null);
    setResult(null);
    try {
      const picked = await pickStatement();
      if (!picked) return;
      const data = await previewCsv.mutateAsync(picked.content);
      setFile(picked);
      setPreview(data);
      setMapping(data.suggested_mapping ?? EMPTY);
      if (!newName) setNewName(picked.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : typeof err === "string" ? err : "Could not read that file.");
    }
  }

  async function runImport() {
    if (!file || !preview) return;
    setError(null);
    try {
      let accountId: number;
      if (choice === "new") {
        if (!newName.trim()) {
          setError("Give the account a name.");
          return;
        }
        accountId = (await createAccount.mutateAsync({ name: newName.trim(), type: newType, institution: "", currency: "USD" })).id;
        setAccountChoice(String(accountId));
      } else {
        accountId = Number(choice);
      }
      setResult(await importCsv.mutateAsync({ account_id: accountId, filename: file.name, content: file.content, mapping }));
      setFile(null);
      setPreview(null);
      onDone?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import failed.");
    }
  }

  const set = (patch: Partial<Mapping>) => setMapping((m) => ({ ...m, ...patch }));
  const problem = mappingProblem(mapping);
  const busy = importCsv.isPending || createAccount.isPending;
  const columnOptions = (
    <>
      <option value={NONE}>Not used</option>
      {preview?.headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </>
  );

  return (
    <Card>
      <CardTitle hint="The file is read on this Mac and never uploaded">Import a CSV statement</CardTitle>

      {!preview && (
        <div className="flex flex-col items-start gap-3">
          <Button variant="primary" onClick={() => void chooseFile()} disabled={previewCsv.isPending}>
            <FileUp size={14} /> Choose CSV file…
          </Button>
          <p className="text-xs text-ink-3">
            Export a statement from your bank's website as CSV. Columns are detected automatically and you can
            correct them before anything is saved.
          </p>
        </div>
      )}

      {preview && file && (
        <div className="flex flex-col gap-5">
          <p className="text-[13px] text-ink-2">
            <span className="font-medium text-ink">{file.name}</span> · {preview.row_count} rows
            {!preview.suggested_mapping && " · columns were not recognized, please map them"}
          </p>

          <div className="grid grid-cols-3 gap-3">
            <Field label="Import into">
              <Select value={choice} onChange={(e) => setAccountChoice(e.target.value)} aria-label="Import into">
                <option value="new">New account…</option>
                {existing.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </Field>
            {choice === "new" && (
              <>
                <Field label="Account name">
                  <Input value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={80} />
                </Field>
                <Field label="Type">
                  <Select value={newType} onChange={(e) => setNewType(e.target.value as typeof newType)}>
                    <option value="checking">Checking</option>
                    <option value="savings">Savings</option>
                    <option value="credit_card">Credit card</option>
                    <option value="other">Other</option>
                  </Select>
                </Field>
              </>
            )}
          </div>

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Column mapping</h3>
            <div className="grid grid-cols-4 gap-3">
              <Field label="Date">
                <Select aria-label="Date column" value={mapping.date} onChange={(e) => set({ date: e.target.value })}>
                  {columnOptions}
                </Select>
              </Field>
              <Field label="Date format">
                <Select value={mapping.date_format} onChange={(e) => set({ date_format: e.target.value })}>
                  {(preview.date_formats ?? []).map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Description">
                <Select
                  aria-label="Description column"
                  value={mapping.description}
                  onChange={(e) => set({ description: e.target.value })}
                >
                  {columnOptions}
                </Select>
              </Field>
              <Field label="Pending status">
                <Select value={mapping.status ?? NONE} onChange={(e) => set({ status: e.target.value || null })}>
                  {columnOptions}
                </Select>
              </Field>
              <Field label="Amount (single column)">
                <Select
                  aria-label="Amount column"
                  value={mapping.amount ?? NONE}
                  onChange={(e) => set({ amount: e.target.value || null, ...(e.target.value ? { debit: null, credit: null } : {}) })}
                >
                  {columnOptions}
                </Select>
              </Field>
              {mapping.amount ? (
                <Field label="Sign convention">
                  <Select
                    value={mapping.amount_convention}
                    onChange={(e) => set({ amount_convention: e.target.value as Mapping["amount_convention"] })}
                  >
                    <option value="negative_is_outflow">Negative = money out</option>
                    <option value="positive_is_outflow">Positive = money out (some cards)</option>
                  </Select>
                </Field>
              ) : (
                <>
                  <Field label="Debit (money out)">
                    <Select aria-label="Debit column" value={mapping.debit ?? NONE} onChange={(e) => set({ debit: e.target.value || null })}>
                      {columnOptions}
                    </Select>
                  </Field>
                  <Field label="Credit (money in)">
                    <Select aria-label="Credit column" value={mapping.credit ?? NONE} onChange={(e) => set({ credit: e.target.value || null })}>
                      {columnOptions}
                    </Select>
                  </Field>
                </>
              )}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-2 text-ink-2">
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h} className="px-3 py-2 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.slice(0, 5).map((row, i) => (
                  <tr key={i} className="border-t border-line">
                    {preview.headers.map((h) => (
                      <td key={h} className="max-w-64 truncate px-3 py-1.5 text-ink">
                        {row[h]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center gap-3">
            <Button variant="primary" disabled={busy || !!problem} onClick={() => void runImport()}>
              {busy ? "Importing…" : `Import ${preview.row_count} rows`}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setPreview(null);
                setFile(null);
              }}
            >
              Cancel
            </Button>
            {problem && <span className="text-xs text-ink-2">{problem}</span>}
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4">
          <Notice tone="critical">{error}</Notice>
        </div>
      )}
      {result && (
        <div className="mt-4">
          <Notice tone="info">
            Imported <b>{result.rows_inserted}</b> new transactions.{" "}
            {result.rows_duplicate > 0 && `${result.rows_duplicate} were already present and skipped. `}
            {result.pending_settled > 0 && `${result.pending_settled} pending transactions settled. `}
            {result.rows_invalid > 0 &&
              `${result.rows_invalid} rows could not be read (rows ${result.invalid_row_numbers.slice(0, 8).join(", ")}).`}
          </Notice>
        </div>
      )}
    </Card>
  );
}
