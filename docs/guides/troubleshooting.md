# Troubleshooting

| Symptom | Cause / action |
| --- | --- |
| `ModuleNotFoundError: applications` / `logs` | SLAI root is not on the path; start via `python run_slaifi.py` from the SLAI root or install SLAIFI inside SLAI. |
| UI says "Illustrative data" | `SLAIFI_MARKET_PROVIDER=mock`. Set `twelvedata` and a key for real quotes. |
| "Mock provider forbidden" at start | `SLAIFI_ENVIRONMENT=production` with the mock provider. |
| Rate-limited / unavailable provider | The UI shows the last cached data with its age or an error; nothing is invented. Retry later. |
| Market closed | Quotes show the last session; orders are refused unless `SLAIFI_PAPER_ALLOW_CLOSED_MARKET_EXECUTION=true`. |
| Order rejected: stale/unavailable data | Quote older than `SLAIFI_PAPER_MAX_QUOTE_AGE_SECONDS` or none available. |
| Order rejected: hard limit | See the listed reasons (position size, volatility cap, cash reserve, prohibited asset class). Change the strategy through the Advisor/Strategies page. |
| 403 `client_header_required` on writes | Custom API clients must send `X-SLAIFI-Client: <anything>`. |
| "Storage not ok" / orders refused | Open Settings → ledger health; restore a backup from the data folder. |
| SLAI explanation says unavailable/disabled | SLAI runtime missing or disabled. Deterministic results are unaffected. |
| Intervals other than Daily missing | The active provider (mock) only supplies daily bars. |
