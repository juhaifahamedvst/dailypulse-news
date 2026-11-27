#!/usr/bin/env bash
# check_api.sh: can we reach a web API? Checks DNS, then TCP, then HTTP, and names the layer that failed.
# Usage: ./check_api.sh URL                for example: ./check_api.sh http://localhost:8000/menu.json
# Exit codes: 0 all good, 2 bad usage, 3 DNS failed, 4 TCP failed, 5 HTTP error status
set -euo pipefail

readonly TIMEOUT=5   # seconds; never wait for ever on the network

say() { printf '%-4s %s\n' "$1" "$2"; }   # results go to stdout
fail() {                                  # problems go to stderr, with an exit code
  echo "check_api: $2" >&2
  exit "$1"
}

split_url() {   # sets scheme, host and port from a URL such as https://api.quickbite.example/orders
  local url="$1"
  [[ "$url" =~ ^(https?)://([^/:]+)(:([0-9]+))?(/.*)?$ ]] || fail 2 "not an http(s) URL: $url"
  scheme="${BASH_REMATCH[1]}"
  host="${BASH_REMATCH[2]}"
  port="${BASH_REMATCH[4]}"
  if [[ -z "$port" ]]; then
    if [[ "$scheme" == "https" ]]; then port=443; else port=80; fi
  fi
}

check_dns() {   # name -> IP address, the way programs on this computer look it up
  ip="$(getent ahosts "$host" | awk 'NR == 1 { print $1 }')" || true
  [[ -n "$ip" ]] || fail 3 "DNS: no address for $host"
  say DNS "ok   $host -> $ip"
}

check_tcp() {   # can we open a TCP connection to the port? (bash's /dev/tcp trick)
  timeout "$TIMEOUT" bash -c "exec 3<>/dev/tcp/$ip/$port" 2>/dev/null ||
    fail 4 "TCP: nothing answers on $ip port $port"
  say TCP "ok   port $port is open"
}

check_http() {   # does the web server answer with a good status code?
  local code
  code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time "$TIMEOUT" "$url")" || fail 5 "HTTP: no answer from $url"
  [[ "$code" =~ ^[23] ]] || fail 5 "HTTP: $url answered $code"
  say HTTP "ok   $code from $url"
}

main() {
  [[ $# -eq 1 ]] || fail 2 "usage: check_api.sh URL"
  url="$1"
  split_url "$url"
  check_dns
  check_tcp
  check_http
}

main "$@"
