# Troubleshooting

Problems with the docs fail the run while planning, before anything changes
in Confluence. Title clashes are also shown on the file in GitHub.

## Title clashes

**"…would be published as 'X', but the space already has a page with that
title…"**
Another page in the space, which this repo didn't create, already has that
title. The error says who made it and where it is. Either retitle your doc
(the error says how), or, if that page should become your doc, rename or
delete it in Confluence first.

**"…and … would both be titled 'X'…"**
Two of your docs have the same title. Retitle one.

**"…changes its title to 'X', which the page for … still has. Swap or reuse
titles in two commits."**
Two docs swapped titles, or a doc took the title of one you removed. Do it in
two commits: first give one doc a temporary title, then the final one.

**"…has an empty title"** or **"…Confluence allows 255"**
A title is blank, or too long once `title-prefix` is added. Change the title
the error points at.

**"…has both README.md and index.md…"**
Only one file can be a folder's own page. Merge them into one.

**"…would replace the content of the root page…"**
The root page has hand-written content, and `adopt-root` is off. Turn it on
for one run, or remove the top-level `README.md` to leave the root page alone.

**"…already publishes into it. Point this repo at another root page."**
Another repo publishes into that root page. Each root page belongs to one
repo.

## Links, images and diagrams

**"link '…' points to …, which is not in the docs"**
A relative link points at a file that isn't in the docs folder. Fix the path,
or use a full URL for files elsewhere in the repo.

**"image '…' not found"** or **"…is outside the docs folder"**
Images must exist and be inside the docs folder.

**"two images named '…'; rename one"**
Two images on one page share a file name. Attachments are named by file name,
so rename one.

**"a Mermaid diagram failed to render"**
The diagram has a syntax error. The lines after it are Mermaid's own error.

**"symlinked folders aren't supported"** or **"links to a file outside the
docs folder"**
Only real files inside the docs folder can be published.

## Access

**AWS: "Not authorized to perform sts:AssumeRoleWithWebIdentity"**
The repo or branch isn't on the publishing role's trust list. See
[Publish a repo's docs](publish-a-repo.md).

**Confluence 401**
The token is wrong or expired. SRE rotates it (see
[Security and access](security.md)).

**Confluence 403 on a page**
Someone restricted that page, or its root page, without the
`confluence-docs-publishers` group. Add the group to the restriction.

**Warning: "Pages not restricted"**
The service account can't set page restrictions yet. Publishing still works;
the pages it created stay editable by anyone who can edit the space until it
can, and later runs restrict them.
