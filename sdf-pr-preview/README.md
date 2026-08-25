# PR Preview — Composite Action

Builds and publishes a per-PR preview environment for org-member PRs. On every push to an open PR it builds the Docker image, pushes it to ECR, labels the PR with `preview` so ArgoCD's ApplicationSet picks it up, and comments the preview URL. When the PR closes (merged or not), it removes the label and comments that the preview was torn down. ArgoCD does the actual deploying — this action only produces the image and the signal.

## How it works

1. **PR closed?** Remove the `preview` label and comment "torn down". Nothing else runs.
2. **Org-membership gate.** A GitHub App token checks whether the PR author is a member of the org (`GITHUB_TOKEN` cannot read org membership). The gate applies to every PR — branch or fork — so an org member's fork PR gets a preview while an outside contributor's does not.
3. **Non-member PR:** any stale `preview` label is removed. This keeps CI authoritative — a hand-applied label cannot create a preview for an image that was never built.
4. **Member PR:** check out the PR head SHA (not the synthetic merge commit), build the image, push it to ECR as `<registry>/<ecr-repository>:pr-<number>-<head-sha>`, then — only after the push succeeds — add the `preview` label and comment `https://<preview-host>` on the PR.

ECR authentication (OIDC, role assumption, registry login) is handled internally via [`stellar/actions/sdf-ecr-login`](../sdf-ecr-login).

## Usage

Composite actions cannot declare triggers, permissions, or concurrency — the caller workflow must provide them exactly as below.

```yaml
# .github/workflows/pr-preview.yml

name: pr-preview

on:
  pull_request_target:
    types: [opened, synchronize, reopened, closed]

# pull_request_target runs in base-repo context, so these are real write
# permissions even for fork PRs. That is the entire reason this event is used:
# on `pull_request`, fork runs get no OIDC token and a read-only token.
permissions:
  contents: read
  id-token: write        # OIDC -> AWS. Silently ignored on `pull_request` forks.
  pull-requests: write   # labels + comments

# A rapid second push cancels the in-flight build rather than racing it.
concurrency:
  group: pr-preview-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: stellar/actions/sdf-pr-preview@main
        with:
          app-id: ${{ vars.PREVIEW_BOT_APP_ID }}
          private-key: ${{ secrets.PREVIEW_BOT_PRIVATE_KEY }}
          ecr-repository: dev/stellar-design-system
          preview-host: design-system-pr-${{ github.event.pull_request.number }}.preview.stellar.org
```


Either way, the action itself checks out the PR **head** SHA before building, replacing the workspace. The build always runs against the contributor's actual commit, and that SHA is what the ApplicationSet must inject as `{{ .head_sha }}`.

## Inputs

| Input | Required | Description |
|---|---|---|
| `app-id` | yes | GitHub App ID used to check org membership |
| `private-key` | yes | Private key of that GitHub App |
| `ecr-repository` | yes | ECR repository to push the preview image to (e.g. `dev/stellar-design-system`) |
| `preview-host` | yes | Hostname the preview will be served on; commented on the PR as `https://<preview-host>` |

## Prerequisites

- **`preview` label** — must already exist in the repo; the action adds/removes it but does not create it.
- **GitHub App** — installed on the org, with permission to read organization members. Its ID and private key are passed as `app-id` / `private-key`.
- **ArgoCD ApplicationSet** — a PR generator watching the repo for the `preview` label, deploying `<registry>/<ecr-repository>:pr-{{ .number }}-{{ .head_sha }}` and routing `preview-host` to it. The label is applied only after the image push succeeds, so the ApplicationSet never renders an Application whose image does not exist yet.
- **AWS OIDC** — the repo must be able to assume the ECR push role used by [`sdf-ecr-login`](../sdf-ecr-login) (hence `id-token: write`).
- **Dockerfile** — at the repo root; the image is built with `context: .` using Buildx with GitHub Actions cache (`type=gha`).

## Security notes

The workflow runs on `pull_request_target`, which executes in the base repo's context with real secrets and write permissions — including for fork PRs. This is safe here because:

- No fork code is checked out or executed before the org-membership gate; the App token is only ever handled by trusted steps.
- The PR head is checked out only for PRs authored by org members, and only to `docker build` it — no repo scripts are run directly on the runner.
- Do not add steps to the caller workflow that run PR-controlled code before the action.

## Teardown

Teardown on close is technically redundant with the ApplicationSet generator (a closed PR leaves its result set anyway), but removing the label explicitly makes it immediate and leaves a trace in the PR timeline.
