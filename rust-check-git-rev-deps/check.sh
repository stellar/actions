#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

# Get repo and sha's of all dependencies in the current cargo workspace that are
# git references containing a revision/commit sha.
cargo metadata --format-version 1 --no-deps \
  | jq -r '[.packages[].dependencies] | flatten | [.[] | .source | select(. != null) | select(. | startswith("git+")) | select(. | contains("?rev=")) | sub("^git\\+"; "") | split("?rev=")] | unique | sort | .[] | @tsv' \
  | while IFS=$'\t' read -r repo sha; do
    # For each, clone the repo, checkout the default branch and tags, and check
    # that the commit can be found in at least one of them.
    temp=$(mktemp -d)
    echo -e "\033[1;34mChecking "$repo" @ "$sha"\033[0m"
    git clone "$repo" "$temp"
    pushd "$temp"
    found=0
    for ref in . $(git tag); do
      git -c advice.detachedHead=false checkout "$ref"
      branch="$(git describe --all)"
      echo -e "\033[1;33mChecking is in "$branch"\033[0m"
      if git merge-base --is-ancestor HEAD "$sha"; then
        echo -e "\033[1;32mCommit is in the history of $branch.\033[0m"
        found=1
      else
        echo -e "\033[1;31mCommit is NOT in the history of $branch.\033[0m"
      fi
    done
    if (( $found == 0 )); then
      echo -e "\033[1;31mDependency revisions must reference a version of the dependency that is on the default branch, or a tag, so that they do not become orphaned.\033[0m"
    fi
    popd
  done
