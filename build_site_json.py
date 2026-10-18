import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from chs_client import current_hour_utc, get_db

OUT_PATH = "docs/live.json"
LOOKBACK_HOURS = 72
HORIZON_HOURS = 48
LEAD_BUCKETS = [0, 1, 2, 3, 6, 12, 18, 24, 30, 36, 42, 48]
HOUR_MEAN_CENTRE = pd.Timedelta(minutes=30)
MAX_RUN_AGE_HOURS = 24


def query(conn, sql, params=(), time_cols=()):
    df = pd.read_sql_query(sql, conn, params=params)
    for col in time_cols:
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def db_time(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def points(times, values):
    return [[f"{t:%Y-%m-%dT%H:%M:%SZ}", round(float(v), 3)]
            for t, v in zip(times, values) if np.isfinite(v)]


def latest_run(conn, table, value_col, now, extra_cols=""):
    latest = conn.execute(f"SELECT MAX(poll_time) FROM {table} WHERE poll_time <= ? AND poll_time >= ?",
                          (db_time(now), db_time(now - timedelta(hours=MAX_RUN_AGE_HOURS)))).fetchone()[0]
    if latest is None:
        return None, None
    df = query(conn, f"SELECT valid_time, {value_col}{extra_cols} FROM {table} WHERE poll_time = ? "
                     f"ORDER BY valid_time", (latest,), ["valid_time"])
    return latest, df


def mae_by_lead(errors, lead):
    buckets = pd.cut(lead, LEAD_BUCKETS)
    grouped = (errors.abs() * 100).groupby(buckets, observed=False)
    return grouped.mean(), grouped.count()


def accuracy(conn):
    chs = query(conn, """SELECT f.poll_time, f.lead_hours, f.wlf - o.wlo AS err FROM wlf f
                         JOIN wlo o ON o.time = f.valid_time WHERE f.lead_hours >= 1""", time_cols=["poll_time"])
    own = query(conn, """SELECT f.poll_time, f.lead_hours, f.own - o.wlo AS err FROM own f
                         JOIN wlo_top o ON o.time = f.valid_time WHERE f.lead_hours >= 1""", time_cols=["poll_time"])
    issued_by_both = own.merge(chs, on=["poll_time", "lead_hours"], suffixes=("_model", "_chs"))
    model_mae, n = mae_by_lead(issued_by_both["err_model"], issued_by_both["lead_hours"])
    chs_mae, _ = mae_by_lead(issued_by_both["err_chs"], issued_by_both["lead_hours"])
    chs_all_mae, chs_all_n = mae_by_lead(chs["err"], chs["lead_hours"])

    def cm(x):
        return None if pd.isna(x) else round(float(x), 2)

    rows = [{"lead": f"{lo}–{hi} h", "model_mae_cm": cm(model_mae.iloc[i]), "chs_mae_cm": cm(chs_mae.iloc[i]),
             "n": int(n.iloc[i]), "chs_all_time_mae_cm": cm(chs_all_mae.iloc[i]), "chs_all_time_n": int(chs_all_n.iloc[i])}
            for i, (lo, hi) in enumerate(zip(LEAD_BUCKETS, LEAD_BUCKETS[1:]))]
    return {
        "forecasts_compared": int(issued_by_both["poll_time"].nunique()),
        "first_compared": db_time(issued_by_both["poll_time"].min()) if len(issued_by_both) else None,
        "chs_all_time_since": db_time(chs["poll_time"].min()) if len(chs) else None,
        "by_lead": rows,
    }


def main():
    now = current_hour_utc()
    start, end = now - timedelta(hours=LOOKBACK_HOURS), now + timedelta(hours=HORIZON_HOURS)
    conn = get_db()   # creates any missing tables, so a fresh db still produces a valid file

    wlo = query(conn, "SELECT time, wlo FROM wlo WHERE time >= ? AND time <= ? ORDER BY time",
                (db_time(start), db_time(now)), ["time"])
    wlp = query(conn, "SELECT time, wlp FROM wlp WHERE time >= ? AND time <= ? ORDER BY time",
                (db_time(start), db_time(end)), ["time"])
    chs_issued, chs = latest_run(conn, "wlf", "wlf", now)
    own_issued, own = latest_run(conn, "own", "own", now, ", weather_run")

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "station": "Pointe-du-Chêne, NB (CHS 01804)",
        "units": "metres above chart datum",
        "window": {"start": db_time(start), "end": db_time(end)},
        "series": {
            "observed": points(wlo["time"] + HOUR_MEAN_CENTRE, wlo["wlo"]),
            "tide": points(wlp["time"], wlp["wlp"]),
            "chs_forecast": chs_issued and {
                "issued": chs_issued, "points": points(chs["valid_time"] + HOUR_MEAN_CENTRE, chs["wlf"])},
            "model_forecast": own_issued and {
                "issued": own_issued, "weather_run": own["weather_run"].iloc[0],
                "points": points(own["valid_time"], own["own"])},
        },
        "accuracy": accuracy(conn),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)

    acc = out["accuracy"]
    print(f"Wrote {OUT_PATH}: {len(out['series']['observed'])} observed, {len(out['series']['tide'])} tide points; "
          f"CHS run {chs_issued}, model run {own_issued}; {acc['forecasts_compared']} forecasts compared head to head.")


if __name__ == "__main__":
    main()
