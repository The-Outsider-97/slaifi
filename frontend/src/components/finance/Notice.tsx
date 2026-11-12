import type { ReactNode } from "react";

type NoticeProps = {
  tone?: "error" | "warning" | "info" | "success";
  title?: string;
  children?: ReactNode;
  onRetry?: () => void;
};

/** Inline message. Errors are announced to assistive technology; the rest are polite status text. */
export function Notice({ tone = "info", title, children, onRetry }: NoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div className="notice__body">
        {title ? <strong>{title}</strong> : null}
        {children ? <span>{children}</span> : null}
      </div>
      {onRetry ? (
        <button type="button" className="secondary-button notice__retry" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="data-state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="data-state">
      <strong>{title}</strong>
      {children ? <span>{children}</span> : null}
    </div>
  );
}

export function Simulated() {
  return (
    <span className="simulated-chip" title="Paper trading: nothing here involves real money.">
      SIMULATED
    </span>
  );
}
