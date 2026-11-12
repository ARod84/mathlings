#!/usr/bin/env bash
# Fetches the os-taxonomy dataset into backend/vendor/os-taxonomy at the pinned commit.
# The pin is TAXONOMY_COMMIT in app/taxonomy/constants.py; this script only reads it.
set -euo pipefail

backend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$backend_dir/app/taxonomy/constants.py"
target="$backend_dir/vendor/os-taxonomy"

commit="$(sed -n 's/^TAXONOMY_COMMIT = "\([0-9a-f]\{40\}\)"$/\1/p' "$constants")"
repo_url="$(sed -n 's/^TAXONOMY_REPO_URL = "\(.*\)"$/\1/p' "$constants")"
if [ -z "$commit" ] || [ -z "$repo_url" ]; then
  echo "Could not read TAXONOMY_COMMIT and TAXONOMY_REPO_URL from $constants" >&2
  exit 1
fi

# The data files are plain git blobs, so Git LFS is not needed.
export GIT_LFS_SKIP_SMUDGE=1

if [ ! -d "$target/.git" ]; then
  mkdir -p "$target"
  git -C "$target" init --quiet
  git -C "$target" remote add origin "$repo_url"
fi

# Fetch exactly the pinned commit, never a branch.
git -C "$target" fetch --quiet --depth 1 origin "$commit"
git -C "$target" -c advice.detachedHead=false checkout --quiet --force "$commit"

actual="$(git -C "$target" rev-parse HEAD)"
if [ "$actual" != "$commit" ]; then
  echo "Checkout is at $actual, expected $commit" >&2
  exit 1
fi
echo "os-taxonomy is at $commit in $target"
