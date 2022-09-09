# stellar/actions
This repository contains GitHub Actions and GitHub Actions Workflows that are shared by [@stellar] repositories.

| Name | Type | Description | Example Use |
| ---- | ---- | ----------- | ----------- |
| [rust-cache] | Action | Caches dependencies, install artifacts, and build artifacts in Rust projects. | [rs-stellar-env] |
| [rust-set-rust-version] | Reusable Workflow | Updates the rust-version in Rust crates to the latest stable version. | [rs-stellar-env] |
| [rust-bump-version] | Reusable Workflow | Updates the version in Rust crates to a input version. | [rs-stellar-env] |
| [rust-publish-dry-run] | Action | Run a package verification on all crates in a workspace in their published form. | [rs-stellar-env] |
| [rust-publish] | Action | Publish all crates in a workspace. | [rs-stellar-env] |

[@stellar]: https://github.com/stellar

[rust-cache]: ./rust-cache/action.yml
[rust-set-rust-version]: ./.github/workflows/rust-set-rust-version.yml
[rust-bump-version]: ./.github/workflows/rust-bump-version.yml
[rust-publish-dry-run]: ./.github/workflows/rust-publish-dry-run.yml
[rust-publish]: ./.github/workflows/rust-publish.yml

[rs-stellar-env]: https://github.com/stellar/rs-stellar-env

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
