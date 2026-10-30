# Confluence Docs Publisher

The Confluence Docs Publisher publishes Markdown from a GitHub repo to
Confluence. Docs are written next to the code they describe, reviewed in pull
requests, and published here automatically when they merge.

Publishing goes one way. GitHub is the source of truth, so to change a
published page, change its Markdown file in GitHub, not the page.

These pages are published by the publisher itself, from
`stellar/actions/confluence-publish/confluence`.

## Pages

- [Publish a repo's docs](publish-a-repo.md): set up publishing for a repo.
- [Writing docs](writing-docs.md): folders, titles, links, images and diagrams.
- [How publishing works](how-it-works.md): which pages it changes, and when.
- [Security and access](security.md): the token, who can publish, and page restrictions.
- [Troubleshooting](troubleshooting.md): what each error means and how to fix it.
- [Design choices](design-choices.md): the opinions built into it, and why.
- [Rendering examples](rendering-examples.md): what each kind of Markdown looks like here.

## At a glance

- **Where it lives:** the GitHub Action `stellar/actions/confluence-publish`.
- **What it needs per repo:** a root page in Confluence, a workflow file, and
  the repo on the publishing role's trust list in `stellar/terraform`.
- **Owner:** SRE.
