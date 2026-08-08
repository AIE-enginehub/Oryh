import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../i18n";

export function NotFoundPage() {
  const { t } = useI18n();
  const location = useLocation();
  const requestedPath = `${location.pathname}${location.search}`;

  return (
    <section className="panel not-found-page" aria-labelledby="not-found-title">
      <span className="eyebrow">404 · {t("pageNotFound")}</span>
      <h2 id="not-found-title">{t("pageNotFound")}</h2>
      <p>{t("notFoundDescription")} <code>{requestedPath}</code></p>
      <Link className="button primary" to="/dashboard">{t("returnDashboard")}</Link>
    </section>
  );
}
