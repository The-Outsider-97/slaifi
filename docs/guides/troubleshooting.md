# Troubleshooting

| Symptom | Cause / action |
| --- | --- |
| `ModuleNotFoundError: applications` / `logs` | Start from the SLAI root with `python -m applications.slaifi` (`python run_slaifi.py` no longer exists). |
| `The web client is not built` | Run `npm.cmd run build` in `applications\slaifi`, then start again. |
| Browser says the page needs the link SLAIFI printed | Open the full link from the terminal (it contains `?token=...`) or restart SLAIFI for a new one. |
| `could not start ... Is another copy already running?` | Port 8777 is taken. Stop the other copy or use `--port`. |
| UI says **NOT AVAILABLE** | No source answered and nothing was saved yet. Set at least one `SLAIFI_<SOURCE>_API_KEY`, restart, then Settings → Check providers. |
| UI says **LAST KNOWN DATA** | Every source failed just now; SLAIFI shows the last real observation it saved, with its time. Open Settings → Market data sources for each source's last problem. Orders on such prices are refused. |
| A source shows *API key rejected* | The key was refused (401/403). Fix the variable and restart; the status persists until restart. |
| A source's last problem says *the free plan does not include this data* | The free plan excludes that symbol/interval (e.g. some FMP symbols, Twelve Data intervals). The next source is used. |
| A source shows *Paused after an error until …* | It was rate-limited or unreachable and is paused until the time shown; SLAIFI also stops calling a source whose free quota is used up. It resumes by itself. Add more sources or raise `SLAIFI_MARKET_LIMITS` on a paid plan. |
| "Check providers" says *Working* but a symbol is empty | That source may not cover the symbol; the others are tried. International symbols are mostly not on free plans. |
| Market closed | Quotes show the last session; orders are refused unless `SLAIFI_PAPER_ALLOW_CLOSED_MARKET_EXECUTION=true`. |
| Order rejected: stale/unavailable data | Quote older than `SLAIFI_PAPER_MAX_QUOTE_AGE_SECONDS` or none available. |
| Order rejected: hard limit | See the listed reasons (position size, volatility cap, cash reserve, prohibited asset class). Change the strategy through the Advisor/Strategies page. |
| 403 `client_header_required` on writes | Custom API clients must send `X-SLAIFI-Client: <anything>`. |
| "Storage not ok" / orders refused | Open Settings → ledger health; restore a backup from the data folder. |
| SLAI explanation says unavailable/disabled | SLAI runtime missing or disabled. Deterministic results are unaffected. |
| Intervals other than Daily missing | Only some sources supply intraday bars (Twelve Data). Without that key only daily/weekly/monthly are offered. |
