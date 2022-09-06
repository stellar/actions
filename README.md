# stellar/actions
This repository contains GitHub Actions and GitHub Actions Workflows that are shared by [@stellar] repositories.

| Name | Type | Description | Example Use |
| ---- | ---- | ----------- | ----------- |
| [rust-cache] | Action | Caches dependencies, install artifacts, and build artifacts in Rust projects. | [rs-stellar-env] |
| [rust-set-rust-version] | Workflow | Updates the rust-version in Rust crates to the latest stable version. | [rs-stellar-env] |

[@stellar]: https://github.com/stellar

[rust-cache]: ./rust-cache/action.yaml
[rust-set-rust-version]: ./rust-cache/workflow.yaml

[rs-stellar-env]: https://github.com/stellar/rs-stellar-env
