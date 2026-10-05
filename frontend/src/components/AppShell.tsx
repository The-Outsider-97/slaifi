import {
  useState,
  type ReactNode,
} from "react";

import {
  Sidebar,
} from "./Sidebar";
import {
  TopBar,
} from "./TopBar";

export type AppPage =
  | "market"
  | "portfolio";

type AppShellProps = {
  children: ReactNode;
  currentPage: AppPage;
};

export function AppShell({
  children,
  currentPage,
}: AppShellProps) {
  const [
    menuOpen,
    setMenuOpen,
  ] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar
        open={menuOpen}
        currentPage={currentPage}
        onNavigate={() =>
          setMenuOpen(false)
        }
      />

      <div className="workspace-shell">
        <TopBar
          currentPage={
            currentPage
          }
          onMenuToggle={() =>
            setMenuOpen(
              (open) => !open,
            )
          }
        />

        {menuOpen ? (
          <button
            className="sidebar-scrim"
            type="button"
            aria-label="Close navigation"
            onClick={() =>
              setMenuOpen(false)
            }
          />
        ) : null}

        {children}
      </div>
    </div>
  );
}
