# ECR image scan — Composite Action

Installs `ecr-scan`, which scans a local container image with Amazon Inspector, the scanner behind ECR enhanced scanning, and reports the critical CVEs ECR would report for it: it uses Inspector's own severity and skips lockfile dev dependencies, as ECR does.

The action logs in to `github-actions-inspector-scan`, which can only call `inspector-scan:ScanSbom`, so it can't push or read images. [`sdf-ecr-login`](../sdf-ecr-login)'s `ecr-push` runs the same scan before every push.

## Usage

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: stellar/actions/ecr-scan@main
  - run: |
      docker build -t my-image .
      ecr-scan my-image
```

```
ecr-scan <image>
```

The action installs `inspector-sbomgen` next to it; elsewhere, `ecr-scan` downloads it for each run. Either way it's a pinned release whose SHA-256 is checked before it runs. It prints one `<CVE>: <packages>` line per critical CVE, then `critical findings: <n>`, and exits 0 with no critical findings, 1 with some, and 2 if the scan couldn't run.

## Inputs

| Name | Required | Default | Description |
|------|----------|---------|-------------|
| `copilot` | no | `false` | Set to `true` in Copilot coding agent setup steps. Installs `ecr-scan` in `/usr/local/bin`, with sbomgen already downloaded since the agent's firewall blocks it, and saves the credentials to `~/.aws`, since the agent's session doesn't inherit the job's environment. They last an hour. |

## Copilot coding agent

With these setup steps, Copilot can scan the images it builds and rescan after each fix:

```yaml
# .github/workflows/copilot-setup-steps.yml
name: Copilot setup steps
on:
  workflow_dispatch:
  push:
    paths: [.github/workflows/copilot-setup-steps.yml]
  pull_request:
    paths: [.github/workflows/copilot-setup-steps.yml]
jobs:
  copilot-setup-steps:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v6
      - uses: stellar/actions/ecr-scan@main
        with:
          copilot: 'true'
```

The agent's firewall must also allow `inspector-scan.us-east-1.amazonaws.com`: add it under the repository's (or organization's) Settings → Copilot → Coding agent → Internet access.
