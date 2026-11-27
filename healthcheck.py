"""Docker's health check for the news API: exit status 0 if /healthz answers 200, else 1.

The slim Python image has no curl, so Python asks instead. The Dockerfile's HEALTHCHECK
runs this every 10 seconds inside the container.
"""

import sys
import urllib.request

URL = "http://127.0.0.1:8000/healthz"


def main() -> int:
    try:
        with urllib.request.urlopen(URL, timeout=2) as response:
            return 0 if response.status == 200 else 1
    except OSError as error:  # refused, timed out, or an HTTP error such as 503
        print(f"unhealthy: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
