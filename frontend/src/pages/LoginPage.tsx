import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError, browserLogin, requestOwnPasswordReset } from "../api/client";
import { LanguageSwitcher, useI18n } from "../i18n";
import { OryhLogo } from "../components/OryhLogo";
import { adoptNewIdentity } from "../session/sessionController";

type LoginLocationState = { from?: string };
type AuthMode = "login" | "reset";

// Replaced at build time by vite's `define` (see vite.config.ts). The typeof
// guard keeps unit tests — which run without that define — from throwing.
const APP_VERSION = typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";

export function LoginPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<AuthMode>(() =>
    new URLSearchParams(location.search).get("mode") === "reset" ? "reset" : "login"
  );

  const login = useMutation({
    mutationFn: browserLogin,
    onSuccess: async () => {
      // The whole cache, not the bootstrap key: everything in it was fetched
      // by whoever was signed in before, and a member signing in after an
      // admin would otherwise read the admin's customers until each query
      // happened to refetch.
      await adoptNewIdentity(queryClient);
      const state = location.state as LoginLocationState | null;
      navigate(state?.from || "/dashboard", { replace: true });
    },
  });

  const resetPassword = useMutation({ mutationFn: requestOwnPasswordReset });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mode === "reset") {
      resetPassword.mutate({ email });
      return;
    }
    login.mutate({ email, password });
  };

  const activeError = mode === "login" ? login.error : resetPassword.error;
  const error = activeError instanceof ApiError
    ? mode === "login" && activeError.status === 401
      ? t("invalidCredentials")
      : activeError.message
    : activeError instanceof Error
      ? activeError.message
      : null;

  const showReset = () => {
    login.reset();
    resetPassword.reset();
    setMode("reset");
    navigate("/login?mode=reset", { replace: true, state: location.state });
  };

  const showLogin = () => {
    resetPassword.reset();
    setMode("login");
    navigate("/login", { replace: true, state: location.state });
  };

  return (
    <main className="login-layout">
      <section className="login-story" aria-label={t("loginProductLabel")}>
        <div className="story-inner">
          <div className="brand-block inverse">
            <OryhLogo subtitle="AI-native business records" />
          </div>
          <div className="story-copy">
            <span className="eyebrow">{t("trustedFactLayer")}</span>
            <h1>{t("loginHero").split("\n").map((line, index) => <span key={line}>{index > 0 && <br />}{line}</span>)}</h1>
            <p>{t("loginBody")}</p>
          </div>
          <div className="security-strip">
            <span>{t("companyDataSeparated")}</span><span>{t("roleBasedAccess")}</span><span>{t("protectedRecords")}</span>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <LanguageSwitcher className="login-language-switcher" />
          <div className="mobile-brand">
            <OryhLogo />
          </div>
          <span className="eyebrow">{t("tenantConsole")}</span>
          <h2>{mode === "login" ? t("loginWorkspace") : t("resetPassword")}</h2>
          <p className="form-intro">
            {mode === "login" ? t("loginIntro") : t("resetPasswordIntro")}
          </p>

          {error && <div className="form-error" role="alert">{error}</div>}

          {mode === "reset" && resetPassword.isSuccess ? (
            <>
              <div className="form-success" role="status">{t("resetEmailSent")}</div>
              <button className="button primary login-submit" type="button" onClick={showLogin}>
                {t("backToSignIn")}
              </button>
            </>
          ) : (
            <>
              <label htmlFor="email">{t("email")}</label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
              />

              {mode === "login" && (
                <>
                  <label htmlFor="password">{t("password")}</label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={t("enterPassword")}
                  />
                  <button className="auth-text-action forgot-password" type="button" onClick={showReset}>
                    {t("forgotPassword")}
                  </button>
                </>
              )}

              <button
                className="button primary login-submit"
                type="submit"
                disabled={mode === "login" ? login.isPending : resetPassword.isPending}
              >
                {mode === "login"
                  ? login.isPending ? t("signingIn") : t("enterConsole")
                  : resetPassword.isPending ? t("sendingResetLink") : t("sendResetLink")}
              </button>

              {mode === "reset" && (
                <button className="auth-text-action reset-back" type="button" onClick={showLogin}>
                  {t("backToSignIn")}
                </button>
              )}
            </>
          )}

          {mode === "login" && (
            <>
              <a className="connector-download" href="/api/v1/connect-skill" download>
                {t("downloadConnectorSkill")} <span aria-hidden="true">↓</span>
              </a>

              <div className="login-links">
                <a href="/home">{t("returnWebsite")}</a>
                <a href="/web/register">{t("registerCompany")}</a>
              </div>
            </>
          )}
          <p className="security-note">{t("securityNote")}</p>
          <p className="login-version" title={`${t("versionLabel")} ${APP_VERSION}`}>
            {t("versionLabel")} {APP_VERSION}
          </p>
        </form>
      </section>
    </main>
  );
}
