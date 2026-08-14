"""
poll_own_forecast.py
---------------------
Hourly snapshot of our own model's published 48h forecast, so it gets
scored by the exact same lead-hour methodology as CHS's wlf. This is the
entire cross-repo dependency between wlf-scorecard and pdu-tide-forecast:
a plain HTTP GET on a public JSON file, no auth, no shared workflow.

pdu-tide-forecast publishes docs/forecast.json on every one of its own
hourly runs, shaped as:
  [{"poll_time": ..., "valid_time": ..., "lead_hours": ..., "prediction": ...}, ...]

Until that repo exists (or on any run where it's down / hasn't produced a
fresh forecast this hour), this script just skips -- it never fails the
workflow. Set OWN_FORECAST_URL once pdu-tide-forecast is live.

Output: appends to data/own_forecast_snapshots.csv
  poll_time    UTC -- when pdu-tide-forecast generated this forecast
  valid_time   UTC
  lead_hours   float
  our_pred     m
"""

import os
import sys
import requests
import pandas as pd

# Set to e.g. "https://<user>.github.io/pdu-tide-forecast/forecast.json" once
# that repo is live. Can also be set via the OWN_FORECAST_URL env var (used
# by the GitHub Actions workflow) so this doesn't need editing per environment.
OWN_FORECAST_URL = os.environ.get("OWN_FORECAST_URL", "")
OUT_PATH = "data/own_forecast_snapshots.csv"


def main():
    if not OWN_FORECAST_URL:
        print("OWN_FORECAST_URL not set -- pdu-tide-forecast isn't live yet. Skipping.")
        sys.exit(0)

    print(f"Fetching own forecast from {OWN_FORECAST_URL}")
    try:
        r = requests.get(OWN_FORECAST_URL, timeout=30)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        print(f"  FAILED: {e}. Skipping this run -- not a fatal error.")
        sys.exit(0)

    if not raw:
        print("  Empty response. Skipping.")
        sys.exit(0)

    df = pd.DataFrame(raw).rename(columns={"prediction": "our_pred"})
    required = {"poll_time", "valid_time", "lead_hours", "our_pred"}
    if not required.issubset(df.columns):
        print(f"  Response missing expected columns {required - set(df.columns)} -- "
              f"got {list(df.columns)}. Skipping (check pdu-tide-forecast's forecast.json shape).")
        sys.exit(0)

    df["poll_time"] = pd.to_datetime(df["poll_time"], utc=True)
    df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
    df = df[["poll_time", "valid_time", "lead_hours", "our_pred"]]

    os.makedirs("data", exist_ok=True)
    if os.path.exists(OUT_PATH):
        existing = pd.read_csv(OUT_PATH, parse_dates=["poll_time", "valid_time"])
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df

    combined = combined.drop_duplicates(subset=["poll_time", "valid_time"], keep="last")
    combined = combined.sort_values(["poll_time", "valid_time"])
    combined.to_csv(OUT_PATH, index=False)

    print(f"  Saved {len(df)} new rows. {OUT_PATH} now has {len(combined):,} total rows.")


if __name__ == "__main__":
    main()
