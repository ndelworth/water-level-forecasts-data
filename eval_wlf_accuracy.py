"""
eval_wlf_accuracy.py
---------------------
The actual point of this repo: turn accumulated snapshots into an honest
"how accurate is each forecast, N hours ahead" answer.

Joins:
  data/wlf_snapshots.csv           (CHS wlf, lead-time tagged)
  data/own_forecast_snapshots.csv  (our model, lead-time tagged, if present)
against:
  data/wlo_actuals.csv             (ground truth)
on valid_time, buckets by lead_hours, and reports MAE / RMSE / bias per
bucket per series.

Also pulls CHS's wlp (pure harmonic tide prediction) fresh for the window
covered by wlo_actuals. wlp isn't a "forecast" in the lead-time sense --
it's the same deterministic value regardless of when you ask -- so it gets
one overall MAE, reported as a flat reference line across every lead
bucket rather than something that degrades with lead time. That's exactly
the baseline that makes "is the surge/weather part of wlf's forecast
actually earning its keep past the tide alone" answerable.

Output:
  data/accuracy_by_lead.csv   long format: series, lead_bucket, mae, rmse, bias, n
  docs/accuracy.json          same data, consumed by docs/index.html
  data/accuracy_by_lead.png   quick-look plot (best-effort; skipped if matplotlib missing)
"""

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

PDU_STATION_ID = "64b6e5ec8027cb190816a0c0"
BASE_URL = f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{PDU_STATION_ID}/data"

WLF_PATH   = "data/wlf_snapshots.csv"
OWN_PATH   = "data/own_forecast_snapshots.csv"
WLO_PATH   = "data/wlo_actuals.csv"
OUT_CSV    = "data/accuracy_by_lead.csv"
OUT_JSON   = "docs/accuracy.json"
OUT_PLOT   = "data/accuracy_by_lead.png"

# Bucket edges in hours -- finer near 0 where we have the most data early on,
# coarser out toward 48h. Right-inclusive: (0,1] is bucket "1h", etc.
BUCKET_EDGES  = [0, 1, 2, 3, 6, 12, 18, 24, 30, 36, 42, 48, 54]
BUCKET_LABELS = [f"{lo}-{hi}h" for lo, hi in zip(BUCKET_EDGES[:-1], BUCKET_EDGES[1:])]
MIN_N = 3  # don't report a bucket until it has at least this many samples


def mae(a, b):  return float(np.mean(np.abs(a - b)))
def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))
def bias(a, b): return float(np.mean(a - b))  # forecast - actual


def load_actuals():
    if not os.path.exists(WLO_PATH):
        print(f"{WLO_PATH} doesn't exist yet -- nothing to score against. "
              f"Let poll_wlo_actuals.py run a few times first.")
        sys.exit(0)
    wlo = pd.read_csv(WLO_PATH, parse_dates=["time"])
    wlo["time"] = pd.to_datetime(wlo["time"], utc=True)
    return wlo.set_index("time")["wlo"]


def score_series(snapshots, actuals, value_col):
    """snapshots: df with poll_time, valid_time, lead_hours, value_col.
    Returns per-bucket mae/rmse/bias/n."""
    df = snapshots.copy()
    df["actual"] = df["valid_time"].map(actuals)
    df = df.dropna(subset=["actual", value_col])
    if df.empty:
        return pd.DataFrame(columns=["lead_bucket", "mae", "rmse", "bias", "n"])

    df["lead_bucket"] = pd.cut(df["lead_hours"], BUCKET_EDGES, labels=BUCKET_LABELS, right=True)
    rows = []
    for bucket, g in df.groupby("lead_bucket", observed=True):
        if len(g) < MIN_N:
            continue
        rows.append({
            "lead_bucket": bucket,
            "mae":  round(mae(g[value_col].values, g["actual"].values) * 100, 2),   # cm
            "rmse": round(rmse(g[value_col].values, g["actual"].values) * 100, 2),  # cm
            "bias": round(bias(g[value_col].values, g["actual"].values) * 100, 2),  # cm
            "n":    len(g),
        })
    return pd.DataFrame(rows)


def fetch_wlp_baseline(actuals):
    """Pull CHS's pure harmonic prediction (wlp) for the window covered by
    wlo_actuals and score it as a single flat number -- it's deterministic,
    not lead-time dependent, so there's nothing to bucket."""
    if actuals.empty:
        return None
    start, end = actuals.index.min(), actuals.index.max()
    try:
        r = requests.get(BASE_URL, params={
            "time-series-code": "wlp",
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":   end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "resolution": "ONE_MINUTE",
        }, timeout=30)
        r.raise_for_status()
        raw = r.json()
        if not raw:
            return None
        wlp = pd.DataFrame(raw).rename(columns={"eventDate": "time", "value": "wlp"})
        wlp["time"] = pd.to_datetime(wlp["time"], utc=True)
        wlp = wlp.set_index("time")["wlp"].resample("1h").mean()
    except Exception as e:
        print(f"  wlp baseline fetch failed ({e}) -- skipping, not fatal.")
        return None

    joined = pd.DataFrame({"wlp": wlp, "actual": actuals}).dropna()
    if len(joined) < MIN_N:
        return None
    return {
        "mae":  round(mae(joined["wlp"].values, joined["actual"].values) * 100, 2),
        "rmse": round(rmse(joined["wlp"].values, joined["actual"].values) * 100, 2),
        "bias": round(bias(joined["wlp"].values, joined["actual"].values) * 100, 2),
        "n":    len(joined),
    }


def main():
    actuals = load_actuals()
    print(f"Loaded {len(actuals):,} hourly actuals ({actuals.index.min()} -> {actuals.index.max()})")

    results = []

    if os.path.exists(WLF_PATH):
        wlf = pd.read_csv(WLF_PATH, parse_dates=["poll_time", "valid_time"])
        wlf_scores = score_series(wlf, actuals, "wlf")
        wlf_scores["series"] = "wlf (CHS operational forecast)"
        results.append(wlf_scores)
        print(f"wlf: scored {len(wlf):,} snapshot rows -> {len(wlf_scores)} lead buckets")
    else:
        print(f"{WLF_PATH} not found yet -- skipping wlf scoring.")

    if os.path.exists(OWN_PATH):
        own = pd.read_csv(OWN_PATH, parse_dates=["poll_time", "valid_time"])
        own_scores = score_series(own, actuals, "our_pred")
        own_scores["series"] = "our model"
        results.append(own_scores)
        print(f"our model: scored {len(own):,} snapshot rows -> {len(own_scores)} lead buckets")
    else:
        print(f"{OWN_PATH} not found yet (pdu-tide-forecast not live / not polled) -- skipping.")

    wlp_baseline = fetch_wlp_baseline(actuals)
    if wlp_baseline:
        wlp_rows = pd.DataFrame([{**wlp_baseline, "lead_bucket": b, "series": "wlp (tide-only baseline)"}
                                  for b in BUCKET_LABELS])
        results.append(wlp_rows)
        print(f"wlp baseline: MAE={wlp_baseline['mae']}cm over {wlp_baseline['n']} hours "
              f"(flat reference, not lead-dependent)")

    if not results:
        print("Nothing scored yet -- too early, or no snapshot files exist. Exiting cleanly.")
        sys.exit(0)

    out = pd.concat(results, ignore_index=True)
    out = out[["series", "lead_bucket", "mae", "rmse", "bias", "n"]]

    os.makedirs("data", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bucket_order": BUCKET_LABELS,
        "rows": out.to_dict(orient="records"),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nSaved {OUT_CSV} and {OUT_JSON} ({len(out)} rows)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 5))
        for series, g in out.groupby("series"):
            g = g.set_index("lead_bucket").reindex(BUCKET_LABELS)
            ax.plot(BUCKET_LABELS, g["mae"], marker="o", label=series)
        ax.set_xlabel("Lead time")
        ax.set_ylabel("MAE (cm)")
        ax.set_title("PDU forecast accuracy vs lead time")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.savefig(OUT_PLOT, dpi=150)
        print(f"Saved {OUT_PLOT}")
    except ImportError:
        print("matplotlib not installed -- skipped the plot, CSV/JSON are still complete.")


if __name__ == "__main__":
    main()
