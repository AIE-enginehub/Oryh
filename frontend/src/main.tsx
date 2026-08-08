import { StrictMode, Suspense, lazy } from "react";
import { createRoot, type Root } from "react-dom/client";

import "./entry.css";
import { OryhLogo } from "./components/OryhLogo";

// Console-only entry. The public website is its own project and container
// (../site); nothing here loads marketing code.
const ConsoleRoot = lazy(() => import("./ConsoleRoot"));

declare global {
  interface Window {
    __oryhReactRoot?: Root;
  }
}

const root = window.__oryhReactRoot ?? createRoot(document.getElementById("root")!);
window.__oryhReactRoot = root;

document.title = "Oryh Console";
root.render(
  <StrictMode>
    <Suspense
      fallback={(
        <main className="console-entry-loading" aria-busy="true" aria-label="正在载入 oryh 控制台">
          <OryhLogo />
          <p>正在载入控制台</p>
        </main>
      )}
    >
      <ConsoleRoot />
    </Suspense>
  </StrictMode>,
);
