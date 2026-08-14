import sys
from datetime import timedelta

from chs_client import current_hour_utc, fetch_series, resample_series, get_db, upsert_df, max_time

DISPLAY_LOOKBACK_HOURS = 24
DISPLAY_LOOKAHEAD_HOURS = 48
SAFETY_MARGIN_HOURS = 6

def main():
    now = current_hour_utc()
    display_start = now - timedelta(hours=DISPLAY_LOOKBACK_HOURS)
    horizon = now + timedelta(hours=DISPLAY_LOOKAHEAD_HOURS)

    conn = get_db()
    latest = max_time(conn, "wlp", "time")
    have_recent_coverage = latest is not None and latest >= horizon - timedelta(hours=SAFETY_MARGIN_HOURS)

    if have_recent_coverage:
        start = latest - timedelta(hours=SAFETY_MARGIN_HOURS)
        print(f"Have coverage through {latest.isoformat()} already -- incremental fetch from {start.isoformat()}.")
    else:
        start = display_start
        print("No usable existing coverage (first run, or stale after a gap) -- full backfill.")

    print(f"Polling wlp for {start.isoformat()} -> {horizon.isoformat()}")
    try:
        raw = fetch_series("wlp", start, horizon, resolution="FIFTEEN_MINUTES")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(0)

    df = resample_series(raw, "time", "wlp", "15min")
    if df.empty:
        print("  No usable data returned this run. Skipping.")
        sys.exit(0)

    upsert_df(conn, "wlp", df, time_cols=["time"])
    total = conn.execute("SELECT COUNT(*) FROM wlp").fetchone()[0]

    print(f"  Pulled {len(df)} rows this run. wlp table now has {total:,} total rows.")


if __name__ == "__main__":
    main()
