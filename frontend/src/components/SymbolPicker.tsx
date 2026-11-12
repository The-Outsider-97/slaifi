import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { errorText } from "../services/api";
import { searchInstruments } from "../services/finance";
import type { Instrument } from "../types/finance";

type Props = {
  label: string;
  placeholder?: string;
  /** Called with the chosen symbol (upper case). The picker clears itself afterwards. */
  onPick: (symbol: string) => void;
  disabled?: boolean;
  /** Symbols to leave out of the suggestions (already chosen). */
  exclude?: readonly string[];
};

/** Search instruments by name or ticker; also accepts a ticker typed and confirmed with Enter. */
export function SymbolPicker({ label, placeholder = "Search a name or ticker", onPick, disabled, exclude = [] }: Props) {
  const listId = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Instrument[]>([]);
  const [active, setActive] = useState(-1);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = text.trim();
    if (query.length < 1) {
      setResults([]);
      setNote("");
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setBusy(true);
      searchInstruments(query, controller.signal)
        .then((response) => {
          if (controller.signal.aborted) return;
          setResults(response.results);
          setActive(-1);
          setNote(
            !response.supported
              ? "Search is not available from the configured data sources; type a ticker and press Enter."
              : response.results.length === 0
                ? "No match. Press Enter to try the ticker as typed."
                : "",
          );
        })
        .catch((failure: unknown) => {
          if (controller.signal.aborted) return;
          setResults([]);
          setNote(errorText(failure) || "Search failed. Press Enter to try the ticker as typed.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [text]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const taken = new Set(exclude.map((s) => s.toUpperCase()));
  const shown = results.filter((r) => !taken.has(r.asset.symbol.toUpperCase())).slice(0, 8);

  const choose = (symbol: string) => {
    const clean = symbol.trim().toUpperCase();
    if (!clean) return;
    onPick(clean);
    setText("");
    setResults([]);
    setOpen(false);
    setActive(-1);
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(shown.length - 1, i + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(-1, i - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const picked = shown[active];
      choose(picked ? picked.asset.symbol : text);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div className="symbol-picker" ref={wrapper}>
      <input
        type="search"
        role="combobox"
        aria-label={label}
        aria-expanded={open && (shown.length > 0 || note !== "")}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        maxLength={24}
        placeholder={placeholder}
        value={text}
        disabled={disabled}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {open && text.trim() !== "" && (shown.length > 0 || note !== "" || busy) ? (
        <ul className="symbol-picker__list" id={listId} role="listbox" aria-label={`${label} suggestions`}>
          {busy && shown.length === 0 ? <li className="symbol-picker__note" role="presentation">Searching…</li> : null}
          {shown.map((hit, index) => (
            <li
              key={`${hit.asset.symbol}:${hit.asset.exchange ?? ""}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? "symbol-picker__item symbol-picker__item--active" : "symbol-picker__item"}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(hit.asset.symbol);
              }}
            >
              <strong>{hit.asset.display_symbol}</strong>
              <span>{hit.name ?? ""}</span>
              <small>{[hit.instrument_type, hit.asset.exchange].filter(Boolean).join(" · ")}</small>
            </li>
          ))}
          {note ? <li className="symbol-picker__note" role="presentation">{note}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
