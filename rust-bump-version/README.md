# Rust Release Process using Bump Version

## Usage

To use the bump version workflow:



## Release Process

All the Rust crates at @stellar are released using the same process. The examples in this document use the `rs-soroban-sdk` repo, but the process is the same for them all.

### 1. Bump Version workflow which opens PR

Each Rust repo has a workflow that can be triggered manually, called the `Bump Version` workflow.

See the `rs-soroban-sdk` repo for example.

Go to https://github.com/stellar/rs-soroban-sdk/actions/workflows/bump-version.yml.

Click `Run workflow` and enter the version the crates in the repository should be bumped to.

![](https://i.imgur.com/VS8BQxy.png)

Clicking the green `Run workflow` button will kick off a workflow that updates the versions and opens a PR. Lookout for the PR for the next step.

### 2. Update any deps needed on PR so it passes CI

A PR will be opened that looks something like this:

![](https://i.imgur.com/7Z3am5h.png)

Make any changes to the `release/vX.Y.Z` branch needed to prepare for this release. That will probably involve:
 - Updating the versions of any dependencies that have since been released.
 - Making sure the docs are accurate.

CI will run extra checks on `release/*` branches to verify that when the crates are published their publish will succeed. This means you might see errors on CI that didn't exist before. These errors need resolving.

### 3. Merge PR

When the build is passing and you're ready to release, merge the PR to the main branch.

### 4. Create Release on GitHub

Draft a new release on GitHub for the repository.

The PR will contain a link you can click to create the release. Make sure to create the release after merging, for the commit on the main branch that was the final commit from the PR merging.

### 5. Monitor the publish process

An action will be started to perform the publish. Follow along to make sure it goes smoothly.

https://github.com/stellar/rs-soroban-sdk/actions
