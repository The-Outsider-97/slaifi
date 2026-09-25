type TopBarProps = {
  onMenuToggle: () => void;
};

export function TopBar({ onMenuToggle }: TopBarProps) {
  return (
    <header className="topbar">
      <button className="mobile-menu" type="button" onClick={onMenuToggle} aria-label="Toggle navigation">
        <span aria-hidden="true">☰</span>
      </button>
      <div className="breadcrumb" aria-label="Breadcrumb">
        <span>Workspace</span>
        <span aria-hidden="true">/</span>
        <strong>Market overview</strong>
      </div>
      <div className="topbar__actions">
        <span className="workspace-chip">DEMO WORKSPACE</span>
        <span className="avatar" aria-label="Jean-Erolle Remy">JR</span>
      </div>
    </header>
  );
}
