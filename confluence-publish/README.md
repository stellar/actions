# confluence-publish

Publishes a folder of Markdown from a repo to Confluence Cloud, one way. GitHub
is the source of truth: edits made in Confluence are overwritten the next time
the doc changes.

## Usage

```yaml
name: publish docs
on:
  push:
    branches: [main]
    paths: ["confluence/**"]
  workflow_dispatch:
permissions:
  id-token: write   # to sign in to AWS and read the Confluence token
  contents: read
concurrency: confluence-publish
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          persist-credentials: false  # nothing here needs git credentials
      - uses: stellar/actions/confluence-publish@main
        with:
          folder: confluence
          root-page: "<root page id>"
```

To check docs on pull requests without publishing (no credentials needed):

```yaml
      - uses: stellar/actions/confluence-publish@main
        with:
          folder: confluence
          check-only: "true"
```

## Inputs

| Input | Default | |
| --- | --- | --- |
| `folder` | `confluence` | Folder of Markdown to publish. |
| `root-page` | | ID of the Confluence page to publish under. Required unless `check-only`. |
| `title-prefix` | `""` | Put in front of every page title, e.g. `"Horizon: "`. |
| `on-orphan` | `delete` | A page whose file is gone: `delete` (move to the trash) or `keep`. |
| `dry-run` | `false` | Show what would change, change nothing. |
| `adopt-root` | `true` | Publish the folder's `README.md` into a root page that has content this publisher did not write. Set `false` to refuse to overwrite a hand-written root page. |
| `editors-group-id` | ID of `confluence-docs-publishers` | ID of the only Confluence group that may edit the pages the publisher creates. The service account must be in it. Empty turns this off. |
| `mermaid` | `true` | Draw ` ```mermaid ` blocks as images. |
| `check-only` | `false` | Only convert the docs and report problems. No AWS or Confluence access. |
| `base-url` | SDF's Confluence, through Atlassian's API gateway | |
| `role-to-assume` | `arn:aws:iam::746476062914:role/github-actions-confluence-publish` | AWS role that can read the token. |
| `secret-id` | `confluence/docs-publisher` | Secrets Manager secret holding `{"email": ..., "token": ...}`. |

## How access works

The Confluence token lives in AWS Secrets Manager, never in GitHub. The action
signs in to AWS with the job's GitHub OIDC token and reads the secret for the
publish step only. The AWS role (in `stellar/terraform`, `aws/sdf/iam`) trusts
only the default branch of the repos listed on it, so to publish from a new
repo, add it to that role's trust policy.

Pages the publisher creates are restricted so only the `editors-group-id` group can edit
them; anyone who can see the space can still read and comment on them. For
this the service account must be in that group and have the space's
"Restrictions: Add/Delete" permission, and a scoped token needs the
`write:content.restriction:confluence` scope. The restriction is set only on pages it
creates: the root page, and existing pages it takes over, keep their
permissions. Space admins can always edit a page or lift its restriction.

If Confluence refuses to set a restriction (the account lacks that permission
or scope), the run still publishes, with a warning, and leaves those pages
open. Every later run tries again, so once the permission is granted the
pages it created are restricted, whether or not they changed.

## What it does

- Each folder under `folder` becomes a page and each Markdown file a child
  page, under the root page. A page's title comes from `title:` in front
  matter, then the first `# ` heading, then the file name.
- The folder's own `README.md` becomes the root page's content. The root page
  keeps its title unless `README.md` sets `title:`, and is never moved or
  trashed.
- Relative links between docs become page links; links to a heading land on
  it. Relative images are uploaded as attachments. Mermaid diagrams are drawn
  as images. Each page starts with a note linking to its source file.
- It owns everything under the root page and nothing outside it. Pages it
  publishes carry a content property (`confluence-publish`) naming the repo
  and file; only those are updated, moved or trashed. Other pages under the
  root are left alone, unless one has the same title as a doc, in which case
  the doc is published into it. A title clash with a page outside the root
  fails the run before anything changes, and the error is shown on the file.
- Unchanged pages are not re-saved, but their images are checked and put back
  if they were removed. Moving or renaming a file keeps the same page (same ID
  and URL) as long as its title stays the same.
- A page whose file is gone is trashed (`on-orphan: delete`), unless pages this
  repo didn't publish sit under it; then it is kept, so they aren't trashed
  with it.
- Only files inside `folder` are published or uploaded: a symlink that leads
  out of it, or a symlinked folder, is an error.

## Development

```bash
cd confluence-publish
uv run pytest -q
uv run confluence-publish <folder> --check
```

Tests run against an in-memory fake of Confluence (`tests/fake.py`) that
enforces the real rules: unique titles per space, versions that go up by one.
