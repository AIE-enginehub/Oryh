import { messages as chineseMessages } from "./locales/zh-CN/messages";
import { messages as englishMessages } from "./locales/en/messages";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "zh-CN" | "en";

const storageKey = "oryh.console.language";

const messages = {"zh-CN": chineseMessages, en: englishMessages} as const;

export type MessageKey = keyof (typeof messages)["zh-CN"];

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey) => string;
  text: (chinese: string, english: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);
const fallbackI18n: I18nContextValue = {
  language: "zh-CN",
  setLanguage: () => undefined,
  t: (key) => messages["zh-CN"][key],
  text: (chinese) => chinese,
};

function initialLanguage(defaultLanguage?: Language): Language {
  try {
    const saved = window.localStorage.getItem(storageKey);
    if (saved === "zh-CN" || saved === "en") return saved;
  } catch {
    // Private-mode storage failures should not stop the console from loading.
  }
  return defaultLanguage ?? (navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en");
}

export function LanguageProvider({ children, defaultLanguage }: { children: ReactNode; defaultLanguage?: Language }) {
  const [language, setLanguage] = useState<Language>(() => initialLanguage(defaultLanguage));

  useEffect(() => {
    document.documentElement.lang = language;
    try {
      window.localStorage.setItem(storageKey, language);
    } catch {
      // Language selection still applies for this browser session.
    }
  }, [language]);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    t: (key) => messages[language][key],
    text: (chinese, english) => language === "en" ? english : chinese,
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  return context ?? fallbackI18n;
}

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { language, setLanguage, t } = useI18n();
  return (
    <label className={`language-switcher ${className}`.trim()}>
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("language")}
        value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}
      >
        <option value="zh-CN">{t("chinese")}</option>
        <option value="en">{t("english")}</option>
      </select>
    </label>
  );
}
