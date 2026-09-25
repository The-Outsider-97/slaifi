import { ThemeToggle } from "./components/ThemeToggle";
import { HomePage } from "./pages/HomePage";

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="/" aria-label="SLAIFI home">
          <span className="brand-mark">S</span>
          <span>
            <strong>SLAIFI</strong>
            <small>SLAI Financial Intelligence</small>
          </span>
        </a>
        <nav aria-label="Primary navigation">
          <a aria-current="page" href="/">Home</a>
        </nav>
        <ThemeToggle />
      </header>
      <HomePage />
    </div>
  );
}
