# water-level-forecasts-data

I'd like to be able to compare some water level forecasting models I'm building against the Canadian Hydrological Service's forecasts for [Pointe-du-Chêne](https://tides.gc.ca/en/stations/01804). 

This repo runs hourly and snapshots the published 48h
horizon on every poll, tagging each value with how far ahead it was
predicted. 

## How it fits together

```
poll_wlf_snapshot.py    -> data/wlf_snapshots.csv           (CHS operational forecast, lead-tagged)
poll_wlo_actuals.py     -> data/wlo_actuals.csv              (ground truth)
poll_own_forecast.py    -> data/own_forecast_snapshots.csv   (our model, via pdu-tide-forecast's published forecast.json)
eval_wlf_accuracy.py    -> data/accuracy_by_lead.csv, docs/accuracy.json, data/accuracy_by_lead.png
build_comparison.py     -> docs/comparison.json              (latest wlf run + latest own-model run vs. recent observed)
```

All five run hourly via `.github/workflows/live.yml`, which also commits the
updated `data/*.csv` files (as `wlf-bot`, not a personal commit) and
redeploys `docs/` to GitHub Pages.

`docs/index.html` has two panels: a "latest forecast vs. observed" time
series (reads `comparison.json`) and the MAE-vs-lead-time scorecard (reads
`accuracy.json`). The comparison chart shows the single most recent wlf run
and the single most recent own-model run, not the whole accumulated
history — overlaying every past forecast run would just be a tangle of
overlapping lines.


## One-time setup

1. Push this repo to GitHub (public — GitHub Pages via Actions is free on
   public repos).
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Actions → General → Workflow permissions: **Read and write**
   (so the bot commit in the workflow can push).
4. Once [pdu-tide-forecast](https://github.com/) is live, set a repository
   variable `OWN_FORECAST_URL` (Settings → Secrets and variables → Actions →
   Variables) to its published `forecast.json` URL, e.g.
   `https://<user>.github.io/pdu-tide-forecast/forecast.json`. Nothing else
   needs to change — `poll_own_forecast.py` picks it up automatically.
5. Trigger the workflow manually once (Actions tab → "live" → Run workflow)
   and check the log before trusting the hourly cron.

## Note on early data

`eval_wlf_accuracy.py` only reports a lead-hour bucket once it has at least
3 samples. The near-term buckets (0-3h) fill in within a day; the 24-48h
buckets need the poller running for a couple of days before there's enough
overlap with observed water level to say anything meaningful. That's
expected, not a bug.

## Local run

```
uv sync
uv run python poll_wlf_snapshot.py
uv run python poll_wlo_actuals.py
uv run python eval_wlf_accuracy.py
uv run python build_comparison.py
```
No API keys needed — IWLS is public/unauthenticated.
