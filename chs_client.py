import os
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timezone

PDU_STATION_ID = "64b6e5ec8027cb190816a0c0"
BASE_URL = f"https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/{PDU_STATION_ID}/data"

DB_PATH = "data/tides.db"

SCHEMA = {
    "wlo": ("time TEXT PRIMARY KEY, wlo REAL", ["time"]),
    "wlp": ("time TEXT PRIMARY KEY, wlp REAL", ["time"]),
    "wlf": ("poll_time TEXT, valid_time TEXT, lead_hours REAL, wlf REAL, "
            "PRIMARY KEY (poll_time, valid_time)", ["valid_time"]),
}


def current_hour_utc():
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def fetch_series(series_code, start, end, resolution="ONE_MINUTE"):
    r = requests.get(BASE_URL, params={
        "time-series-code": series_code,
        "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to":   end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolution": resolution,
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def resample_series(raw, time_col, value_col, freq):
    if not raw:
        return pd.DataFrame(columns=[time_col, value_col])

    df = pd.DataFrame(raw).rename(columns={"eventDate": time_col, "value": value_col})
    df[time_col] = pd.to_datetime(df[time_col], utc=True)
    df = df.set_index(time_col)[[value_col]].sort_index().resample(freq).mean().reset_index()
    return df[df[value_col].notna()]


def get_db(path=DB_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    for table, (cols, index_cols) in SCHEMA.items():
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
        for col in index_cols:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table} ({col})")
    conn.commit()
    return conn


def upsert_df(conn, table, df, time_cols):
    df = df.copy()
    for col in time_cols:
        df[col] = pd.to_datetime(df[col], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    cols = list(df.columns)
    placeholders = ",".join("?" * len(cols))
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        df[cols].itertuples(index=False, name=None),
    )
    conn.commit()


def max_time(conn, table, col):
    value = conn.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
    return pd.Timestamp(value, tz="utc") if value else None
