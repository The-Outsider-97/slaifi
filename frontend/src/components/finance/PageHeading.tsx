import type { ReactNode } from "react";

type Props = { kicker: string; title: string; subtitle: string; aside?: ReactNode };

/** Same heading structure as the existing Market overview and My portfolio pages. */
export function PageHeading({ kicker, title, subtitle, aside }: Props) {
  return (
    <header className="page-heading">
      <div>
        <span className="section-kicker">{kicker}</span>
        <h1>
          {title}
          <span>.</span>
        </h1>
        <p>{subtitle}</p>
      </div>
      {aside ? <div className="page-heading__aside">{aside}</div> : null}
    </header>
  );
}
