# stellar/actions

This repository contains GitHub Actions and GitHub Actions Workflows that are
shared by [@stellar] repositories.

## Usage

### Actions

To use an action in this repository in another repository, specify the action in
this repo using the `uses` directive inside a step inside a job, and specify `stellar/actions/<action-directory>`. For example:

```yml
jobs:
  my_job:
    steps:
    - uses: stellar/actions/rust-cache@main
```

### Reusable Workflows

To use a reusable workflow in this repository in another repository, specify the
reusable workflow in this repo using the `uses` directive inside a job, and
specify `stellar/actions/<path-to-reusable-workflow>`. The path used for the
workflow must be the `.github/workflows/` path. For example:

```yml
jobs:
  my_job:
    uses: stellar/actions/.github/workflows/rust-set-rust-version.yml@main
```

## Actions and Workflows

### Rust

#### General

| Name | Type | Description |
| ---- | ---- | ----------- |
| [rust-cache] | Action | Caches dependencies, install artifacts, and build artifacts in Rust projects. |
| [rust-set-rust-version] | Workflow | Updates the rust-version in Rust crates to the latest stable version. |

#### Releasing / Publishing

See [README-rust-release.md] for the release process supported by these
workflows.

| Name | Type | Description |
| ---- | ---- | ----------- |
| [rust-bump-version] | Workflow | Updates the version in Rust crates to a input version. |
| [rust-publish-dry-run] | Workflow | Run a package verification on all crates in a workspace in their published form. |
| [rust-publish] | Workflow | Publish all crates in a workspace. |

### Project Management

| Name | Type | Description |
| ---- | ---- | ----------- |
| [update-completed-sprint-on-issue-closed] | Workflow | Updates the CompletedSprint project field when an issue/PR is closed. |

[@stellar]: https://github.com/stellar

[rust-cache]: ./rust-cache
[rust-set-rust-version]: ./.github/workflows/rust-set-rust-version.yml
[rust-bump-version]: ./.github/workflows/rust-bump-version.yml
[rust-publish-dry-run]: ./.github/workflows/rust-publish-dry-run.yml
[rust-publish]: ./.github/workflows/rust-publish.yml

[README-rust-release.md]: README-rust-release.md
