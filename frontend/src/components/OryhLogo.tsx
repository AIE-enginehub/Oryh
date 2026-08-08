type OryhLogoProps = {
  className?: string;
  subtitle?: string;
};

/** Four connected records around one trusted center. */
export function OryhLogo({ className = "", subtitle }: OryhLogoProps) {
  return (
    <span className={`oryh-logo ${className}`.trim()} aria-label="Oryh">
      <svg className="oryh-symbol" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
        <rect className="oryh-symbol-base" x="7" y="4" width="17" height="8" rx="3" />
        <rect className="oryh-symbol-base" x="28" y="9" width="8" height="17" rx="3" />
        <rect className="oryh-symbol-accent" x="16" y="28" width="17" height="8" rx="3" />
        <rect className="oryh-symbol-base" x="4" y="15" width="8" height="17" rx="3" />
      </svg>
      <span className="oryh-name-stack">
        <span className="oryh-wordmark" aria-hidden="true">ryh</span>
        {subtitle && <span className="oryh-subtitle">{subtitle}</span>}
      </span>
    </span>
  );
}
