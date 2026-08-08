import { useI18n } from "../../i18n";

type RestrictedStateProps = {
  title: string;
  description: string;
};

export function RestrictedState({ title, description }: RestrictedStateProps) {
  const { text } = useI18n();
  return (
    <section className="activity-restricted" role="alert">
      <span className="restricted-mark" aria-hidden="true">!</span>
      <div><span className="eyebrow">{text("访问受限", "Access limited")}</span><h3>{title}</h3><p>{description}</p></div>
    </section>
  );
}
