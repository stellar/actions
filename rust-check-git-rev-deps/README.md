# rust-check-git-rev-deps Action

The rust-check-git-rev-deps action checks that `git` dependencies that are
versioned by a commit sha are not referring to a commit that is likely to become
orphaned.

Commits are accepted by the check if they can be found in one of:
- The history of the default branch of the repository.
- The history of a tag of the repository.

## Usage

```yml
jobs:
  my_job:
    steps:
    - uses: stellar/actions/rust-check-git-rev-deps@main
```
