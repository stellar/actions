# Design choices

The opinions built into the publisher, and why.

## GitHub is the source of truth

Docs are written, reviewed and changed in GitHub. Publishing only goes one
way, from GitHub to Confluence, so there's never a question of which copy is
right. Every page says where its source file is, and once the publishing
account is allowed to set restrictions, pages it creates can only be edited by
the publishing group.

Comments stay in Confluence. Review of the content happens in pull requests.

## It only touches what it made

The publisher changes pages it created, and the root page it's pointed at.
Nothing else: not hand-made pages under its root, not another repo's pages,
not anything elsewhere in the space. When a doc's title is already used by a
page it didn't create, it stops and says which page, instead of overwriting
it.

## It fails before it writes

Everything that can be checked is checked before anything changes in
Confluence: title clashes, broken links, missing images, diagrams that don't
render, titles Confluence would refuse. A run either publishes everything or,
for those problems, nothing. Errors point at the file to change.

## History stays meaningful

- Unchanged pages aren't saved again, so page history only shows real changes.
- Moving or renaming a file keeps the same page, ID and URL, so links,
  comments and incident.io references keep working.
- Every change is a page version naming the repo and commit.
- Deleted docs go to the trash, where they can be restored, never straight to
  permanent deletion.

## Safe by default

- Raw HTML in Markdown is shown as text, so docs can't inject HTML or
  Confluence macros.
- Only files inside the docs folder are published or uploaded. Symlinks that
  lead out of it are refused.
- The Confluence token lives in AWS, is read only by the default branch of
  approved repos, and only the publish step can see it. Pull requests convert
  the docs with no credentials at all.

## Boring Markdown

Docs are CommonMark with tables, strikethrough and links, the same Markdown
GitHub shows. Mermaid diagrams are the one addition, because Confluence can't
draw them. See [Rendering examples](examples/rendering-examples.md) for everything that
renders, and what doesn't.
