"""The news archive's tables and headlines (Chapter 39). Safe to run again and again.

Compose runs it as a one-off service before the API and the worker start: they wait until it
exits with 0 (depends_on with condition: service_completed_successfully).
"""

import sys

import psycopg

from settings import archive_conninfo

TABLES = """
CREATE TABLE IF NOT EXISTS headlines (
    id integer PRIMARY KEY,
    section text NOT NULL,
    title text NOT NULL
);
CREATE TABLE IF NOT EXISTS push_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    text text NOT NULL,
    groups integer NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now()
);
"""

HEADLINES = [
    (9001, "city", "Council approves the new tram line"),
    (9002, "traffic", "Riverside bridge closed this weekend"),
    (9003, "weather", "Snow expected on Thursday night"),
    (9004, "election", "Election 2027: find your polling station"),
    (9005, "election", "Results night: live from 22:00 on Sunday"),
]


def main() -> int:
    with psycopg.connect(archive_conninfo()) as connection:
        connection.execute(TABLES)
        added = 0
        for row in HEADLINES:
            cursor = connection.execute(
                "INSERT INTO headlines VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING", row
            )
            added += cursor.rowcount
        count = connection.execute("SELECT count(*) FROM headlines").fetchone()
    print(f"migrate: tables ready, {added} new headlines, {count[0] if count else 0} in all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
