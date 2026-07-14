import os
import sys
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

PDU_STATION_ID = "64b6e5ec8027cb190816a0c0"
BASE_URL = f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{PDU_STATION_ID}/data"
OUT_PATH = "data/wlf_snapshots.csv"
HORIZON_HOURS = 49


def fetch_wlf(start, end):
    r = requests.get(BASE_URL, params={
        "time-series-code": "wlf",
        "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to":   end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolution": "ONE_MINUTE",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now + timedelta(hours=HORIZON_HOURS)

    print(f"Polling wlf for {now.isoformat()} -> {end.isoformat()}")
    try:
        raw = fetch_wlf(now, end)
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(0)

    if not raw:
        print("  No data returned -- CHS may not have a current forecast run yet. Skipping.")
        sys.exit(0)

    df = pd.DataFrame(raw).rename(columns={"eventDate": "valid_time", "value": "wlf"})
    df["valid_time"] = pd.to_datetime(df["valid_time"], utc=True)
    df = df.set_index("valid_time")[["wlf"]].sort_index().resample("1h").mean().reset_index()
    df = df[df["wlf"].notna()]

    df["poll_time"] = now
    df["lead_hours"] = (df["valid_time"] - now).dt.total_seconds() / 3600.0
    df = df[["poll_time", "valid_time", "lead_hours", "wlf"]]

    os.makedirs("data", exist_ok=True)
    if os.path.exists(OUT_PATH):
        existing = pd.read_csv(OUT_PATH, parse_dates=["poll_time", "valid_time"])
        combined = pd.concat([existing, df], ignore_index=True)
    else:
        combined = df

    combined = combined.drop_duplicates(subset=["poll_time", "valid_time"], keep="last")
    combined = combined.sort_values(["poll_time", "valid_time"])
    combined.to_csv(OUT_PATH, index=False)

    print(f"  Saved {len(df)} new rows (lead_hours {df['lead_hours'].min():.0f}-{df['lead_hours'].max():.0f}h). "
          f"{OUT_PATH} now has {len(combined):,} total rows.")


if __name__ == "__main__":
    main()
