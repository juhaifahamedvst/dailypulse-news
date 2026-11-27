#!/bin/sh
# check_version.sh: the tag being released matches the version written in the code (lesson 40.7).
# Usage: scripts/check_version.sh v1.2.0
set -eu

tag="$1"
want="${tag#v}"
case "$want" in
  [0-9]*.[0-9]*.[0-9]*) ;;
  *) echo "$tag is not a version tag like v1.2.0" >&2; exit 1 ;;
esac

in_code=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' news_api.py)
in_project=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml)
bad=0
if [ "$in_code" != "$want" ]; then
  echo "news_api.py says VERSION = \"$in_code\", but the tag is $tag" >&2
  bad=1
fi
if [ "$in_project" != "$want" ]; then
  echo "pyproject.toml says version = \"$in_project\", but the tag is $tag" >&2
  bad=1
fi
if [ "$bad" -eq 0 ]; then
  echo "tag $tag matches the code: version $want"
fi
exit "$bad"
