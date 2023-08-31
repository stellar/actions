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
      git clone --quiet "$repo" "$temp"
      pushd "$temp" > /dev/null
      found=0
      for ref in HEAD $(git tag); do
        desc="$(git describe --all "$ref")"
        if git merge-base --is-ancestor "$sha" "$ref"; then
          echo -e "\033[1;32mCommit is in the history of $desc.\033[0m"
          found=1
        fi
      done
      if (( $found == 0 )); then
        fails=1
        echo -e "Commit NOT found in the history of the default branch, or any tag."
      fi
      popd > /dev/null
    done
    if (( $fails > 0 )); then
      echo -e "\033[1;31mDependency revisions must reference a version of the dependency that is on the default branch, or a tag, so that they do not become orphaned.\033[0m"
      exit 1
    fi
  }
