import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { StoreProvider } from "./lib/store";

/** Keeps a rendering bug from leaving the user with a blank window. */
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-[13px] text-ink-2">
        <p>Something went wrong while drawing this screen. Your data is unaffected.</p>
        <button
          type="button"
          className="rounded-lg border border-line bg-surface px-3.5 py-2 text-ink"
          onClick={() => window.location.reload()}
        >
          Reload LocalLedger
        </button>
      </div>
    );
  }
}

const queryClient = new QueryClient({
  // networkMode "always": everything is on loopback, so the app must keep working when the
  // Mac is offline and must not pause requests while the window is in the background.
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5000, networkMode: "always" },
    mutations: { networkMode: "always" },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <StoreProvider>
          <App />
        </StoreProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>,
);
