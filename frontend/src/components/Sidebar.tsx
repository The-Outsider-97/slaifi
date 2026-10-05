import {
  type AppPage,
} from "./AppShell";
import {
  ThemeToggle,
} from "./ThemeToggle";

type SidebarProps = {
  open: boolean;
  currentPage: AppPage;
  onNavigate: () => void;
};

function navClass(
  active: boolean,
) {
  return active
    ? "nav-item nav-item--active"
    : "nav-item";
}

export function Sidebar({
  open,
  currentPage,
  onNavigate,
}: SidebarProps) {
  return (
    <aside
      className={
        `sidebar${
          open
            ? " sidebar--open"
            : ""
        }`
      }
      aria-label="Workspace navigation"
    >
      <div className="sidebar__brand">
        <span
          className="brand-mark"
          aria-hidden="true"
        >
          S
        </span>

        <span className="brand-copy">
          <strong>
            SLAIFI
          </strong>
          <small>
            FINANCIAL INTELLIGENCE
          </small>
        </span>
      </div>

      <div className="sidebar__section">
        <span className="sidebar__label">
          WORKSPACE
        </span>

        <nav
          className="sidebar__nav"
          aria-label="Primary navigation"
        >
          <a
            className={navClass(
              currentPage ===
                "market",
            )}
            href="#/market"
            aria-current={
              currentPage ===
              "market"
                ? "page"
                : undefined
            }
            onClick={onNavigate}
          >
            <span
              className="nav-icon"
              aria-hidden="true"
            >
              ▥
            </span>
            <span>
              Market overview
            </span>
          </a>

          <a
            className={navClass(
              currentPage ===
                "portfolio",
            )}
            href="#/portfolio"
            aria-current={
              currentPage ===
              "portfolio"
                ? "page"
                : undefined
            }
            onClick={onNavigate}
          >
            <span
              className="nav-icon"
              aria-hidden="true"
            >
              ▣
            </span>
            <span>
              My portfolio
            </span>
          </a>

          <a
            className="nav-item"
            href="#academy"
            onClick={onNavigate}
          >
            <span
              className="nav-icon"
              aria-hidden="true"
            >
              ▤
            </span>
            <span>
              SLAI Academy
            </span>
          </a>
        </nav>
      </div>

      <div className="sidebar__spacer" />

      <section
        className="clarity-card"
        id="academy"
        aria-label="SLAIFI guidance"
      >
        <span
          className="spark-icon"
          aria-hidden="true"
        >
          ✧
        </span>

        <strong>
          Clarity before action.
        </strong>

        <p>
          Understand the signal.
          <br />
          Know the risk.
        </p>
      </section>

      <ThemeToggle />

      <div className="sidebar__user">
        <span
          className="avatar avatar--small"
          aria-hidden="true"
        >
          JR
        </span>

        <span>
          <strong>
            Jean-Erolle Remy
          </strong>
          <small>
            Personal workspace
          </small>
        </span>
      </div>
    </aside>
  );
}
