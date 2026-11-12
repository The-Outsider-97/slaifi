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

const NAV_ITEMS: {
  page: AppPage;
  href: string;
  label: string;
  icon: string;
}[] = [
  { page: "market", href: "#/market", label: "Market overview", icon: "▥" },
  { page: "analysis", href: "#/analysis", label: "Stock analysis", icon: "◔" },
  { page: "portfolio", href: "#/portfolio", label: "My portfolio", icon: "▣" },
  { page: "paper", href: "#/paper", label: "Paper trading", icon: "⇄" },
  { page: "advisor", href: "#/advisor", label: "SLAI Advisor", icon: "✦" },
  { page: "strategy", href: "#/strategy", label: "Strategies & goals", icon: "◎" },
  { page: "settings", href: "#/settings", label: "Settings", icon: "⚙" },
];

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
          {NAV_ITEMS.map((item) => (
            <a
              key={item.page}
              className={navClass(
                currentPage === item.page,
              )}
              href={item.href}
              aria-current={
                currentPage === item.page
                  ? "page"
                  : undefined
              }
              onClick={onNavigate}
            >
              <span
                className="nav-icon"
                aria-hidden="true"
              >
                {item.icon}
              </span>
              <span>
                {item.label}
              </span>
            </a>
          ))}

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
