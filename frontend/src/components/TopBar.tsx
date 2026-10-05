import type {
  AppPage,
} from "./AppShell";

type TopBarProps = {
  currentPage: AppPage;
  onMenuToggle: () => void;
};

const PAGE_NAMES:
  Record<AppPage, string> = {
    market: "Market overview",
    portfolio: "My portfolio",
  };

export function TopBar({
  currentPage,
  onMenuToggle,
}: TopBarProps) {
  return (
    <header className="topbar">
      <button
        className="mobile-menu"
        type="button"
        onClick={onMenuToggle}
        aria-label="Toggle navigation"
      >
        <span aria-hidden="true">
          ☰
        </span>
      </button>

      <div
        className="breadcrumb"
        aria-label="Breadcrumb"
      >
        <span>
          Workspace
        </span>

        <span aria-hidden="true">
          /
        </span>

        <strong>
          {
            PAGE_NAMES[
              currentPage
            ]
          }
        </strong>
      </div>

      <div className="topbar__actions">
        <span className="workspace-chip">
          SLAIFI WORKSPACE
        </span>

        <span
          className="avatar"
          aria-label="Jean-Erolle Remy"
        >
          JR
        </span>
      </div>
    </header>
  );
}
