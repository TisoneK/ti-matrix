/* The one container every view is made of: a titled panel with a scrolling body. */

import { ReactNode } from "react";

export function Panel({ title, meta, actions, children, grow, className }: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  grow?: boolean;
  className?: string;
}) {
  return (
    <section className={`panel${grow ? " grow" : ""}${className ? ` ${className}` : ""}`}>
      <header className="head">
        <h2>{title}</h2>
        <span className="spacer" />
        {meta ? <span className="hint">{meta}</span> : null}
        {actions}
      </header>
      {children ? <div className="body">{children}</div> : null}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
