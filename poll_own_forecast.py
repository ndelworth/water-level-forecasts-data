import json
import sys

import pandas as pd

from chs_client import get_db, upsert_df


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "forecast.json"
    try:
        with open(path) as f:
            forecast = json.load(f)
    except FileNotFoundError:
        print(f"No {path} -- the model didn't produce a forecast this run. Skipping.")
        sys.exit(0)

    df = pd.DataFrame(forecast["forecast"]).rename(columns={"water_level": "own"})
    df["poll_time"] = forecast["issued"]
    df["weather_run"] = forecast["weather_run"]
    df = df[["poll_time", "valid_time", "lead_hours", "own", "weather_run"]]

    conn = get_db()
    upsert_df(conn, "own", df, time_cols=["poll_time", "valid_time"])
    total = conn.execute("SELECT COUNT(*) FROM own").fetchone()[0]
    print(f"Saved {len(df)} rows issued {forecast['issued']} (IFS run {forecast['weather_run']}). "
          f"own table now has {total:,} total rows.")


if __name__ == "__main__":
    main()
