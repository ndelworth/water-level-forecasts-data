import sys
from datetime import timedelta

from chs_client import current_hour_utc, fetch_series, resample_series, get_db, upsert_df

HORIZON_HOURS = 49


def main():
    now = current_hour_utc()
    end = now + timedelta(hours=HORIZON_HOURS)

    print(f"Polling wlf for {now.isoformat()} -> {end.isoformat()}")
    try:
        raw = fetch_series("wlf", now, end)
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(0)

    df = resample_series(raw, "valid_time", "wlf", "1h")
    if df.empty:
        print("  No data returned -- CHS may not have a current forecast run yet. Skipping.")
        sys.exit(0)

    df["poll_time"] = now
    df["lead_hours"] = (df["valid_time"] - now).dt.total_seconds() / 3600.0
    df = df[["poll_time", "valid_time", "lead_hours", "wlf"]]

    conn = get_db()
    upsert_df(conn, "wlf", df, time_cols=["poll_time", "valid_time"])
    total = conn.execute("SELECT COUNT(*) FROM wlf").fetchone()[0]

    print(f"  Saved {len(df)} new rows (lead_hours {df['lead_hours'].min():.0f}-{df['lead_hours'].max():.0f}h). "
          f"wlf table now has {total:,} total rows.")


if __name__ == "__main__":
    main()
