import glob
import json
import os
import sqlite3

DB_PATH = "docs/tides.db"
CHUNK_DIR = "docs/tides_chunks"
URL_PREFIX = "https://ndelworth.github.io/water-level-forecasts-data/tides_chunks/tides.sqlite3."
SERVER_CHUNK_SIZE = 10 * 1024 * 1024
SUFFIX_LENGTH = 3


def main():
    conn = sqlite3.connect(DB_PATH)
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()

    os.makedirs(CHUNK_DIR, exist_ok=True)
    for f in glob.glob(f"{CHUNK_DIR}/tides.sqlite3.*"):
        os.remove(f)

    total_bytes = os.path.getsize(DB_PATH)
    n_chunks = 0
    with open(DB_PATH, "rb") as f:
        while True:
            chunk = f.read(SERVER_CHUNK_SIZE)
            if not chunk:
                break
            with open(f"{CHUNK_DIR}/tides.sqlite3.{n_chunks:0{SUFFIX_LENGTH}d}", "wb") as out:
                out.write(chunk)
            n_chunks += 1

    config = {
        "serverMode": "chunked",
        "requestChunkSize": page_size,
        "databaseLengthBytes": total_bytes,
        "serverChunkSize": SERVER_CHUNK_SIZE,
        "urlPrefix": URL_PREFIX,
        "suffixLength": SUFFIX_LENGTH,
    }
    with open(f"{CHUNK_DIR}/config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"Split {DB_PATH} ({total_bytes:,} bytes) into {n_chunks} chunk(s) of up to {SERVER_CHUNK_SIZE:,} bytes each.")


if __name__ == "__main__":
    main()
