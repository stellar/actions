# Page nesting

Folders become pages, and the files in them become their child pages. This
part of the tree comes from:

```text
examples/
  README.md                        → "Examples"
  page-nesting/
    README.md                      → "Page nesting" (this page)
    a-child-page.md                → "A child page"
    folder-without-a-readme/       → "Folder without a readme"
      a-grandchild-page.md         → "A grandchild page"
```

- **A folder's `README.md`** is that folder's page. Without one, the folder
  still gets a page, titled from its name, that just lists what's in it.
- **Every folder page lists its children** at the bottom, so nobody has to
  keep an index up to date by hand.
- **Order** is folders first, then files, alphabetically, the same on every
  publish.
- **Titles are prefixed** (`Docs Publisher: ` here) because titles are unique
  across the whole space; the prefix keeps generic names like "A child page"
  from clashing with anyone else's.
- **Moving a file** to another folder moves the same page under its new
  parent, with the same ID and URL.

See [A child page](a-child-page.md), or go down another level to
[A grandchild page](folder-without-a-readme/a-grandchild-page.md).
