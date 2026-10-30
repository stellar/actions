# Writing docs

## Folders become pages

```text
confluence/
  README.md            → the root page's content
  runbook.md           → page "Runbook"
  alerts/
    README.md          → page "Alerts" (the folder's own page)
    ledger-age.md      → child page "Ledger age"
    img/diagram.png    → uploaded as an attachment
```

- Each Markdown file becomes a page, and each folder becomes a page with the
  folder's files as its children.
- A folder's `README.md` becomes the folder page's content. Without one, the
  folder page just lists its children.
- The top-level `README.md` becomes the root page's content. Without one, the
  root page is left alone.

## Titles

A page's title comes from, in order:

1. `title:` in the file's front matter,
2. its first `# ` heading,
3. its file name (`ledger-age.md` → "Ledger age").

```markdown
---
title: Ledger age alert
---
```

Titles are unique across the whole Confluence space, not just under your root
page. If a title is already taken by a page the publisher didn't create, the
run fails and says which page. Use the workflow's `title-prefix` to keep your
repo's titles apart from everyone else's.

## Links

- Link to another doc with a relative path: `[runbook](runbook.md)`. It
  becomes a link to that doc's page.
- Link to a heading: `[failover](runbook.md#failover)`. It lands on that
  heading.
- A relative link to a file that doesn't exist fails the run, so broken links
  are caught in the pull request. A link to another file in the repo, outside
  the docs folder, goes to that file on GitHub.
- Links to websites are left as they are. A bare `https://...` address or an
  email address becomes a link on its own; `www.example.com` without
  `https://` doesn't.

## Images

Use relative paths: `![diagram](img/diagram.png)`. Images are uploaded as
attachments to the page. They must be inside the docs folder, and two images
on one page can't share a file name.

## Diagrams

Fenced `mermaid` blocks are drawn as images:

````markdown
```mermaid
flowchart LR
  A[Merge to main] --> B[Publish] --> C[Confluence]
```
````

A diagram that fails to render fails the run, with Mermaid's error.

## Code blocks

Fenced code blocks become Confluence code blocks, with the language you give
them (` ```bash `, ` ```yaml `).

## What not to put in docs

Published pages are visible to anyone who can see the space. Runbooks that
name internal hosts, accounts or where secrets are stored belong in an
internal or private repo, never a public one. Never put secrets in docs.
