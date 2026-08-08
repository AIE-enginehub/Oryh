import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function ConsoleRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/console">
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default ConsoleRoot;
