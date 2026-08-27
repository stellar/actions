# PR Preview — Composite Actions

Per-PR preview environments for org-member PRs, deployed by ArgoCD. On every push to an open PR the flow builds the preview image(s), pushes them to ECR, labels the PR with `preview` so ArgoCD's ApplicationSet picks it up, and comments the preview URL. When the PR closes (merged or not), it removes the label and comments that the preview was torn down. ArgoCD does the actual deploying — these actions only produce the images and the signal.

The flow is two actions that bracket your build, so your repo owns how its images are built (Makefiles, multiple images, non-root Dockerfiles) without weakening the security model:

| Step | Who | Role |
|---|---|---|
| [`sdf-pr-preview/gate`](./gate) | this repo | **Policy.** Withdraws the `preview` label, handles teardown on close, checks org membership. Outputs `member` and `image-tag`. Must run before any PR code is touched. |
| build & push | your workflow | Checkout PR head, build, push — every step guarded by `member == 'true'`, every image tagged with `image-tag`. |
| [`sdf-pr-preview/publish`](./publish) | this repo | **Signal.** Verifies every image exists in the registry, then adds the label and comments the URL. |

## How it works

1. **Withdraw the signal** (`gate`). On every event, the `preview` label is removed first. The ApplicationSet derives `head_sha` from the live PR, so a label left over from a previous build would otherwise let it deploy `pr-<number>-<new-sha>` before that image is pushed — and point at a nonexistent tag for as long as that commit stays the head if the build fails. Removing it up front makes the signal fail closed: the label is present only while the images it implies exist. The tradeoff is that the preview goes dark while a rebuild is in flight.
2. **PR closed?** (`gate`) The removal above is the teardown; a "torn down" comment is added and `member` is `false`, so nothing else runs.
3. **Org-membership gate** (`gate`). A GitHub App token checks that the PR author, the actor who triggered the run, and the head-repo owner are all members of the org (`GITHUB_TOKEN` cannot read org membership). The gate applies to every PR — branch or fork — so an org member's fork PR gets a preview while an outside contributor's does not. Non-member PRs stop here: the up-front removal already revoked any stale or hand-applied label, so CI stays authoritative.
4. **Build and push** (your workflow). Check out the PR head SHA — not the synthetic merge commit — build, and push each image as `<registry>/<repository>:<image-tag>`, where `image-tag` is `pr-<number>-<head-sha>`.
5. **Publish** (`publish`). Confirm every listed image exists in the registry (`docker manifest inspect`), then — and only then — restore the `preview` label and comment `https://<preview-host>` on the PR. A failed or cancelled build, a miswired build step, or a mismatched tag all leave the label off, never a broken preview.

There is one residual window: between a push landing and the workflow's first step running (typically seconds), the generator can observe the new `head_sha` with the previous run's label still attached and briefly render an Application for a not-yet-pushed tag. This self-heals as soon as the label removal runs; the ApplicationSet should tolerate a transiently missing image rather than treat it as fatal.

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
      # 1. Policy. Nothing that touches PR code may run before this.
      - id: gate
        uses: stellar/actions/sdf-pr-preview/gate@main
        with:
          app-id: ${{ vars.PREVIEW_BOT_APP_ID }}
          private-key: ${{ secrets.PREVIEW_BOT_PRIVATE_KEY }}

      # 2. Your build. EVERY step from here on is guarded by the gate.
      #    Check out the PR head SHA, never the default base ref.
      - uses: actions/checkout@v4
        if: steps.gate.outputs.member == 'true'
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          persist-credentials: false

      - id: ecr
        if: steps.gate.outputs.member == 'true'
        uses: stellar/actions/sdf-ecr-login@main

      - name: Build and push preview images
        if: steps.gate.outputs.member == 'true'
        env:
          ECR_SERVER_TAG: ${{ steps.ecr.outputs.ecr-registry }}/dev/myapp-server:${{ steps.gate.outputs.image-tag }}
          ECR_CLIENT_TAG: ${{ steps.ecr.outputs.ecr-registry }}/dev/myapp-client:${{ steps.gate.outputs.image-tag }}
        run: |
          export SERVER_TAG=${ECR_SERVER_TAG}
          make docker-build-server
          docker push ${SERVER_TAG}

          export CLIENT_TAG=${ECR_CLIENT_TAG}
          make docker-build-client
          docker push ${CLIENT_TAG}

      # 3. Signal. Verifies both images exist, then labels + comments.
      - uses: stellar/actions/sdf-pr-preview/publish@main
        if: steps.gate.outputs.member == 'true'
        with:
          images: |
            ${{ steps.ecr.outputs.ecr-registry }}/dev/myapp-server:${{ steps.gate.outputs.image-tag }}
            ${{ steps.ecr.outputs.ecr-registry }}/dev/myapp-client:${{ steps.gate.outputs.image-tag }}
          preview-host: myapp-pr-${{ github.event.pull_request.number }}.preview.stellar.org
```

A single-image repo is the same shape with one image: build it however you like (`docker build`, `docker/build-push-action`, `make`), tag it with `steps.gate.outputs.image-tag`, push it, and list it in `publish`'s `images`.

### Caller contract

The trust boundary lives in your workflow, so these are not optional:

- `gate` runs **first**. No step before it may check out or execute PR code.
- **Every** step after `gate` — checkout, registry login, build, push, `publish` — carries `if: steps.gate.outputs.member == 'true'`. A missing guard on the checkout means an outsider's fork is built under `pull_request_target` with a live OIDC token in the job.
- Checkout uses `ref: ${{ github.event.pull_request.head.sha }}` and `persist-credentials: false`. The default checkout on `pull_request_target` is the base ref, which would build the wrong code.
- Every preview image is tagged with `steps.gate.outputs.image-tag`, verbatim, and listed in `publish`'s `images`. That tag is what the ApplicationSet renders; a hand-rolled tag that drifts from it fails the existence check rather than deploying nothing.
- Log in to the registry before `publish` runs. The existence check reuses the docker credentials your push already needed.

## Inputs and outputs

### `sdf-pr-preview/gate`

| Input | Required | Description |
|---|---|---|
| `app-id` | yes | GitHub App ID used to check org membership |
| `private-key` | yes | Private key of that GitHub App |

| Output | Description |
|---|---|
| `member` | `'true'` when the event is not `closed` and the PR author, triggering actor, and head-repo owner are all org members; otherwise `'false'` |
| `image-tag` | `pr-<number>-<head-sha>` — the tag every preview image must carry |

### `sdf-pr-preview/publish`

| Input | Required | Description |
|---|---|---|
| `images` | yes | Fully qualified image references (`registry/repository:tag`), one per line; every one must exist before the label is applied |
| `preview-host` | yes | Hostname the preview will be served on; commented on the PR as `https://<preview-host>` |

## Prerequisites

- **`preview` label** — must already exist in the repo; the actions add/remove it but do not create it.
- **GitHub App** — installed on the org, with permission to read organization members. Its ID and private key are passed as `app-id` / `private-key`.
- **ArgoCD ApplicationSet** — a PR generator watching the repo for the `preview` label, deploying `<registry>/<repository>:pr-{{ .number }}-{{ .head_sha }}` and routing `preview-host` to it. The label is removed while a build is in flight and applied only after every image is confirmed present, so outside the seconds-wide window noted above the ApplicationSet never renders an Application whose image does not exist.
- **AWS OIDC** — the repo must be able to assume the ECR push role used by [`sdf-ecr-login`](../sdf-ecr-login) (hence `id-token: write`).

## Security notes

The workflow runs on `pull_request_target`, which executes in the base repo's context with real secrets and write permissions — including for fork PRs. This is safe because:

- No fork code is checked out or executed before the org-membership gate; the App token is only ever handled by trusted steps inside `gate`.
- The PR head is checked out only for PRs whose author, actor, and head-repo owner are all org members, and only to build it.
- The workflow file and the actions are always taken from the base repo / `stellar/actions@main`, so a fork cannot alter the gate for its own run.
- The guards described in the caller contract are what keep this true. Building before `gate`, or leaving a post-gate step unguarded, executes untrusted code in a privileged job — do not do it.

## Teardown

Teardown on close is technically redundant with the ApplicationSet generator (a closed PR leaves its result set anyway), but removing the label explicitly makes it immediate and leaves a trace in the PR timeline. The same label removal runs at the start of every build, so a preview is also (deliberately) absent while a new head SHA is being built — a failed or cancelled build leaves the preview down rather than pointing at an image that was never pushed.
