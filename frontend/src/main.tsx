import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./index.css";
import { getStoredLang, setLang } from "./lib/i18n";

// Apply stored language preference before first render to prevent FOUC
setLang(getStoredLang());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Market data is updated daily — 5-minute stale time is appropriate
      staleTime: 5 * 60 * 1000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root element not found");

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
