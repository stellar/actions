#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

# Get repo and sha's of all dependencies in the current cargo workspace that are
# git references containing a revision/commit sha.
cargo metadata --format-version 1 --no-deps \
  | jq -r '[.packages[].dependencies] | flatten | [.[] | .source | select(. != null) | select(. | startswith("git+")) | select(. | contains("?rev=")) | sub("^git\\+"; "") | split("?rev=")] | unique | sort | .[] | @tsv' \
  | {
    fails=0
    while IFS=$'\t' read -r repo sha; do
      # For each, clone the repo, checkout the default branch and tags, and check
      # that the commit can be found in at least one of them.
      temp=$(mktemp -d)
      echo -e "\033[1;34mChecking "$repo" @ "$sha"\033[0m"
      git clone "$repo" "$temp"
      pushd "$temp"
      found=0
      for ref in . $(git tag); do
        git -c advice.detachedHead=false checkout "$ref"
        desc="$(git describe --all)"
        echo -e "\033[1;33mChecking is in "$desc"\033[0m"
        if git merge-base --is-ancestor "$sha" HEAD; then
          echo -e "\033[1;32mCommit is in the history of $desc.\033[0m"
          found=1
        else
          echo -e "Commit is NOT in the history of $desc."
        fi
      done
      if (( $found == 0 )); then
        fails=1
      fi
      popd
    done
    if (( $fails > 0 )); then
      echo -e "\033[1;31mDependency revisions must reference a version of the dependency that is on the default branch, or a tag, so that they do not become orphaned.\033[0m"
      exit 1
    fi
  }
