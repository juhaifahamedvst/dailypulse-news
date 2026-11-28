"""Settings for every DailyPulse program: the API, the worker and the migration (Chapter 39).

They come from the environment, as twelve-factor asks (Chapter 37). A secret can come from a file
instead: if NAME_FILE is set, the file it names wins over NAME. The official postgres image uses
the same rule, and Docker Compose mounts each secret as a file in /run/secrets/.
"""

import os
from pathlib import Path

from psycopg.conninfo import make_conninfo


def setting(name: str, default: str | None = None) -> str:
    """NAME_FILE (a secret's file) first, then NAME, then the default. Missing: stop at once."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set (nor {name}_FILE)")
    return value


def archive_conninfo() -> str:
    """How to reach the news archive.

    In the cloud, one connection string: DAILYPULSE_DB_URL (or the file DAILYPULSE_DB_URL_FILE
    names), the way Render hands a database to a web service (Chapter 41). In Compose, four
    parts, and the host is the service's name: db.
    """
    if os.environ.get("DAILYPULSE_DB_URL") or os.environ.get("DAILYPULSE_DB_URL_FILE"):
        return make_conninfo(setting("DAILYPULSE_DB_URL"), connect_timeout=3)
    return make_conninfo(
        host=setting("DAILYPULSE_DB_HOST"),
        dbname=setting("DAILYPULSE_DB_NAME"),
        user=setting("DAILYPULSE_DB_USER"),
        password=setting("DAILYPULSE_DB_PASSWORD"),
        connect_timeout=3,
    )
