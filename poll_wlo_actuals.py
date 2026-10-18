import sys
from datetime import timedelta

from chs_client import current_hour_utc, fetch_series, resample_series, get_db, upsert_df

LOOKBACK_HOURS = 72


def main():
    now = current_hour_utc()
    start = now - timedelta(hours=LOOKBACK_HOURS)

    print(f"Polling wlo for {start.isoformat()} -> {now.isoformat()}")
    try:
        raw = fetch_series("wlo", start, now)
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(0)

    df = resample_series(raw, "time", "wlo", "1h")
    if df.empty:
        print("  No usable data returned this run. Skipping.")
        sys.exit(0)

    conn = get_db()
    upsert_df(conn, "wlo", df, time_cols=["time"])
    total = conn.execute("SELECT COUNT(*) FROM wlo").fetchone()[0]

    print(f"  Pulled {len(df)} hourly rows this run. wlo table now has {total:,} total rows.")

    try:
        raw = fetch_series("wlo", start, now, resolution="SIXTY_MINUTES")
    except Exception as e:
        print(f"  Top-of-hour wlo FAILED: {e}")
        sys.exit(0)
    top = resample_series(raw, "time", "wlo", "1h")
    if not top.empty:
        upsert_df(conn, "wlo_top", top, time_cols=["time"])
        print(f"  Pulled {len(top)} top-of-hour rows. wlo_top table now has "
              f"{conn.execute('SELECT COUNT(*) FROM wlo_top').fetchone()[0]:,} total rows.")


if __name__ == "__main__":
    main()
