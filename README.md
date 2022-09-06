# stellar/actions
This repository contains GitHub Actions and GitHub Actions Workflows that are shared by [@stellar] repositories.

Actions are defined in directories.

Workflows live in `.github/workflows/`.

Actions and workflows are lightly tested in this repo, and those test workflows
live in `.github/workflows/test-*`.

| Name | Type | Description | Example Use |
| ---- | ---- | ----------- | ----------- |
| [rust-cache] | Action | Caches dependencies, install artifacts, and build artifacts in Rust projects. | [rs-stellar-env] |
| [rust-set-rust-version] | Workflow | Updates the rust-version in Rust crates to the latest stable version. | [rs-stellar-env] |
| [rust-bump-version] | Workflow | Updates the version in Rust crates to a input version. | [rs-stellar-env] |

[@stellar]: https://github.com/stellar

[rust-cache]: ./rust-cache/action.yml
[rust-set-rust-version]: ./.github/workflows/rust-set-rust-version.yml
[rust-bump-version]: ./.github/workflows/rust-bump-version.yml

[rs-stellar-env]: https://github.com/stellar/rs-stellar-env
