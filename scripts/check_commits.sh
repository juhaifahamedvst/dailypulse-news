#!/bin/sh
# check_commits.sh: every commit in a pull request follows Conventional Commits (lesson 40.4).
# The rule of Chapter 17's commit-msg hook, run again in CI, where nobody can skip it.
# Usage: scripts/check_commits.sh BASE      for example: scripts/check_commits.sh origin/main
set -eu

base="$1"
bad=0

for commit in $(git rev-list --no-merges "$base..HEAD"); do
  subject=$(git log -1 --format=%s "$commit")
  short=$(git log -1 --format=%h "$commit")
  if ! printf '%s\n' "$subject" | grep -Eq '^[a-z]+(\([a-z0-9-]+\))?!?: .+'; then
    echo "$short \"$subject\": start with a type, like: fix(api): refuse a banner without a key" >&2
    bad=1
  elif [ "${#subject}" -gt 72 ]; then
    echo "$short: keep the first line to 72 characters (this one has ${#subject})" >&2
    bad=1
  fi
done

if [ "$bad" -eq 0 ]; then
  echo "every commit message follows the rule"
fi
exit "$bad"
