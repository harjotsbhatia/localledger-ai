import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type S } from "./client";

const DATA_KEYS = ["accounts", "overview", "transactions", "recurring"];

function useInvalidateData() {
  const client = useQueryClient();
  return () => Promise.all(DATA_KEYS.map((key) => client.invalidateQueries({ queryKey: [key] })));
}

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: () => api<S["Health"]>("/api/health"),
    retry: 5,
    retryDelay: 500,
  });

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => api<S["Settings"]>("/api/settings") });

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: S["SettingsUpdate"]) => api<S["Settings"]>("/api/settings", { method: "PUT", body }),
    onSuccess: (data) => {
      client.setQueryData(["settings"], data);
      void client.invalidateQueries({ queryKey: ["ollama"] });
    },
  });
}

export const useAccounts = () =>
  useQuery({ queryKey: ["accounts"], queryFn: () => api<S["Account"][]>("/api/accounts") });

export const useCategories = () =>
  useQuery({ queryKey: ["categories"], queryFn: () => api<string[]>("/api/categories"), staleTime: Infinity });

export const useOverview = (period: string) =>
  useQuery({
    queryKey: ["overview", period],
    queryFn: () => api<S["Overview"]>("/api/analytics/overview", { params: { period } }),
  });

export const useRecurring = () =>
  useQuery({ queryKey: ["recurring"], queryFn: () => api<S["Recurring"][]>("/api/analytics/recurring") });

export type TxFilters = {
  query?: string;
  category?: string;
  account_id?: number;
  period?: string;
  limit: number;
  offset: number;
};

export const useTransactions = (filters: TxFilters) =>
  useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => api<S["TransactionPage"]>("/api/transactions", { params: filters }),
    placeholderData: (previous) => previous,
  });

export const useOllamaStatus = () =>
  useQuery({
    queryKey: ["ollama", "status"],
    queryFn: () => api<S["OllamaStatus"]>("/api/ollama/status"),
    refetchInterval: 15000,
  });

export const usePullStatus = (active: boolean) =>
  useQuery({
    queryKey: ["ollama", "pull"],
    queryFn: () => api<S["PullStatus"]>("/api/ollama/pull"),
    refetchInterval: active ? 1000 : false,
  });

export function useCreateAccount() {
  const invalidate = useInvalidateData();
  return useMutation({
    mutationFn: (body: S["AccountCreate"]) => api<S["Account"]>("/api/accounts", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useDeleteAccount() {
  const invalidate = useInvalidateData();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/api/accounts/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export const usePreviewCsv = () =>
  useMutation({
    mutationFn: (content: string) =>
      api<S["CsvPreview"]>("/api/imports/preview", { method: "POST", body: { content } }),
  });

export function useImportCsv() {
  const invalidate = useInvalidateData();
  return useMutation({
    mutationFn: (body: S["ImportRequest"]) => api<S["ImportResult"]>("/api/imports", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useLoadDemo() {
  const invalidate = useInvalidateData();
  return useMutation({
    mutationFn: () => api<S["DemoResult"]>("/api/demo/load", { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useDeleteAllData() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/api/data/delete", { method: "POST", body: { confirm: "DELETE" } }),
    onSuccess: () => client.invalidateQueries(),
  });
}

export const useStartPull = () =>
  useMutation({
    mutationFn: (model: string) => api<S["PullStatus"]>("/api/ollama/pull", { method: "POST", body: { model } }),
  });

export const sendChat = (messages: S["ChatTurn"][]) =>
  api<S["AgentResult"]>("/api/chat", { method: "POST", body: { messages } });
