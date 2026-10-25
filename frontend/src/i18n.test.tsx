import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LanguageProvider, LanguageSwitcher, useI18n } from "./i18n";
import { messages as english } from "./locales/en/messages";
import { messages as chinese } from "./locales/zh-CN/messages";

function LanguageProbe() {
  const { t, text } = useI18n();
  return <><h1>{t("loadingConsole")}</h1><p>{text(chinese.chinese, "Chinese")}</p><LanguageSwitcher /></>;
}

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("console locale resources", () => {
  it("retains matching English and Chinese message keys", () => {
    expect(Object.keys(english).sort()).toEqual(Object.keys(chinese).sort());
  });

  it("switches both message APIs and persists the selected language", () => {
    render(<LanguageProvider defaultLanguage="en"><LanguageProbe /></LanguageProvider>);
    expect(screen.getByRole("heading")).toHaveTextContent(english.loadingConsole);
    expect(screen.getByText("Chinese")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "zh-CN" } });
    expect(screen.getByRole("heading")).toHaveTextContent(chinese.loadingConsole);
    expect(screen.getByText(chinese.chinese, { selector: "p" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(window.localStorage.getItem("oryh.console.language")).toBe("zh-CN");
  });

  it("keeps the existing Chinese fallback outside the provider", () => {
    render(<LanguageProbe />);
    expect(screen.getByRole("heading")).toHaveTextContent(chinese.loadingConsole);
  });
});
