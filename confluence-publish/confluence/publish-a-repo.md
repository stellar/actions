# Publish a repo's docs

Setting up a repo takes four steps. After that, every merge to the default
branch that changes the docs publishes them.

## 1. Create the root page

Create an empty page in Confluence where the repo's docs should live, for
example under the service's page. Copy its page ID from the URL
(`/pages/<id>/...`).

The repo's docs are published under this page, and the folder's `README.md`
becomes its content. If the page already has hand-written content, the first
publish replaces it (see `adopt-root` in [How publishing works](how-it-works.md)).

## 2. Let the repo publish

Publishing reads the Confluence token through an AWS role that trusts only
the default branch of the repos listed on it. Add the repo to the role's trust
policy in `stellar/terraform`:

- File: `aws/sdf/iam/iam_roles.auto.tfvars.json`
- Role: `github-actions-confluence-publish`
- Add `repo:stellar/<repo>:ref:refs/heads/<default branch>` to the
  `token.actions.githubusercontent.com:sub` list.

Merge and apply that change with Atlantis before the first publish.

## 3. Add the docs

Put the Markdown in a `confluence/` folder at the top of the repo (or any
folder, set with `folder:`). See [Writing docs](writing-docs.md).

## 4. Add the workflow

Add `.github/workflows/confluence-publish.yml`:

```yaml
name: confluence-publish
on:
  push:
    branches: [main]
    paths: ["confluence/**", ".github/workflows/confluence-publish.yml"]
  pull_request:
    paths: ["confluence/**", ".github/workflows/confluence-publish.yml"]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  # Converts the docs without publishing, so broken links fail the pull request.
  check:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      - uses: stellar/actions/confluence-publish@main
        with:
          folder: confluence
          check-only: "true"

  publish:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # to sign in to AWS and read the Confluence token
      contents: read
    concurrency: confluence-publish
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false
      - uses: stellar/actions/confluence-publish@main
        with:
          folder: confluence
          root-page: "<root page id>"
          title-prefix: "Horizon: "
```

`title-prefix` is optional. Page titles are unique across the whole space, so
a prefix lets several repos each have a "Setup" page.

## Try it first

Run the workflow by hand (Actions → confluence-publish → Run workflow) with
the `dry-run` input set to `true` to see what it would change without
changing anything. Manual runs only work on the default branch, because the
AWS role trusts nothing else.

## Inputs

| Input | Default | |
| --- | --- | --- |
| `folder` | `confluence` | Folder of Markdown to publish. |
| `root-page` | | ID of the page to publish under. Required unless `check-only`. |
| `title-prefix` | `""` | Put in front of every page title. |
| `on-orphan` | `delete` | A page whose file is gone: `delete` (move to the trash) or `keep`. |
| `dry-run` | `false` | Show what would change, change nothing. |
| `adopt-root` | `true` | Publish `README.md` into a root page that has hand-written content. |
| `editors-group-id` | `confluence-docs-publishers` | Only this group may edit pages the publisher creates. Empty turns this off. |
| `mermaid` | `true` | Draw Mermaid blocks as images. |
| `check-only` | `false` | Only convert the docs and report problems. Needs no credentials. |
