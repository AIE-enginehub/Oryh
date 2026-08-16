import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { createConsoleQueryClient } from "./session/sessionController";
import "./styles.css";

// One client for the app's lifetime. Its cache belongs to whoever is signed
// in, and `adoptNewIdentity` is what hands it to the next person — see
// session/sessionController.ts.
const queryClient = createConsoleQueryClient();

export function ConsoleRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary onResetCache={() => queryClient.clear()}>
        <BrowserRouter basename="/console">
          <App />
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export default ConsoleRoot;
