"""Turn a docs folder into the tree of pages to publish.

Every folder under the docs root becomes a page, and so does every Markdown
file in it. A folder's README.md or index.md is that folder's own page. The
docs root itself maps to the root page in Confluence: its README.md (key ".")
becomes that page's content, under the safety rules in sync.py.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

INDEX_NAMES = ("README.md", "index.md")
ROOT_KEY = "."  # the docs folder itself, published into the root page
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
H1 = re.compile(r"^# +(.+?)\s*#*\s*$", re.MULTILINE)


@dataclass
class Node:
    key: str  # path from the docs root, "guides" or "guides/setup.md"
    title: str
    parent: str | None  # key of the parent node; None means the root page
    markdown: str  # body without front matter or the title heading
    source: str | None  # file the body came from, relative to the docs root
    is_folder: bool
    title_from: str = "file name"  # what set the title: see TITLE_FIX
    children: list[str] = field(default_factory=list)

    @property
    def file(self) -> str:
        """The file (or folder) a maintainer edits to change this page."""
        return self.source or self.key

    def how_to_retitle(self) -> str:
        return TITLE_FIX[self.title_from].format(file=self.file)


# How to change a page's title, by what set it.
TITLE_FIX = {
    "front matter": "change `title:` in the front matter of {file}",
    "heading": "change the first `# ` heading of {file}, or add a `title:` to its front matter",
    "file name": "rename {file}, or give it a `# ` heading or a `title:` in front matter",
    "folder name": "rename the folder {file}, or add a README.md to it with a `# ` heading",
    "root page": "rename the root page in Confluence, or set `title:` in the front matter of {file}",
}


class TitleError(ValueError):
    """A title problem, tied to the file that has to change."""

    def __init__(self, message: str, file: str):
        super().__init__(message)
        self.file = file


def split_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("front matter must be a YAML mapping")
    return meta, text[m.end():]


def take_title(text: str, meta: dict, fallback: str) -> tuple[str, str, str]:
    """Pick the page title; return (title, body with a used H1 removed, what set it)."""
    if meta.get("title"):
        return str(meta["title"]).strip(), text, "front matter"
    m = H1.search(_without_code(text))
    if m:
        start = text.find(m.group(0))
        body = text[:start] + text[start + len(m.group(0)):]
        return m.group(1).strip(), body.lstrip("\n"), "heading"
    return fallback, text, "file name"


def _without_code(text: str) -> str:
    """Blank out fenced code so a '# comment' in a code block is not a title."""
    return re.sub(r"^(```|~~~).*?^\1", lambda m: " " * len(m.group(0)), text,
                  flags=re.MULTILINE | re.DOTALL)


def pretty(name: str) -> str:
    stem = name[:-3] if name.endswith(".md") else name
    words = re.sub(r"[-_]+", " ", stem).strip()
    return words[:1].upper() + words[1:]


def _check_links(root: Path) -> None:
    """Only publish what is in the docs folder: no symlinks that lead out of it,
    and no symlinked folders (which could also loop back on themselves)."""
    for dirpath, dirnames, filenames in os.walk(root):  # does not follow symlinks
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if path.is_dir():
                raise ValueError(f"{rel}: symlinked folders aren't supported; use a real folder")
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"{rel}: links to a file outside the docs folder")


def build_tree(root: Path, title_prefix: str = "", root_title: str | None = None) -> dict[str, Node]:
    """Return the nodes keyed by path, parents before children.

    title_prefix goes in front of every title, so repos sharing a space can
    each have a "Setup" page ("Horizon: Setup", "RPC: Setup").
    """
    root = root.resolve()
    _check_links(root)
    nodes: dict[str, Node] = {}

    def add_folder(folder: Path, parent: str | None) -> None:
        for entry in sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if entry.name.startswith("."):
                continue
            rel = PurePosixPath(entry.relative_to(root).as_posix())
            if entry.is_dir():
                if not any(entry.rglob("*.md")):
                    continue
                index = next((entry / n for n in INDEX_NAMES if (entry / n).is_file()), None)
                if index:
                    meta, text = split_front_matter(index.read_text())
                    title, body, title_from = take_title(text, meta, pretty(entry.name))
                    if title_from == "file name":
                        title_from = "folder name"
                    source = index.relative_to(root).as_posix()
                else:
                    title, body, source, title_from = pretty(entry.name), "", None, "folder name"
                key = str(rel)
                nodes[key] = Node(key, title_prefix + title, parent, body, source, True, title_from)
                if parent:
                    nodes[parent].children.append(key)
                add_folder(entry, key)
            elif entry.suffix == ".md" and entry.name not in INDEX_NAMES:
                meta, text = split_front_matter(entry.read_text())
                title, body, title_from = take_title(text, meta, pretty(entry.name))
                key = str(rel)
                nodes[key] = Node(key, title_prefix + title, parent, body, key, False, title_from)
                if parent:
                    nodes[parent].children.append(key)

    index = next((root / n for n in INDEX_NAMES if (root / n).is_file()), None)
    if index:
        # The root page keeps its own title unless front matter sets one: a heading
        # alone never renames a page that someone created by hand.
        meta, text = split_front_matter(index.read_text())
        heading_title, body, title_from = take_title(text, meta, "")
        if title_from == "front matter":
            title = title_prefix + heading_title
        else:
            title, title_from = root_title or heading_title or "Root page", "root page"
        nodes[ROOT_KEY] = Node(ROOT_KEY, title, None, body, index.name, True, title_from)
    add_folder(root, None)
    seen: dict[str, Node] = {}
    for node in nodes.values():
        other = seen.get(node.title.lower())
        if other:
            raise TitleError(
                f"{node.file} and {other.file} would both be titled {node.title!r}, and "
                f"Confluence titles are unique per space. To fix, {node.how_to_retitle()}.",
                node.file)
        seen[node.title.lower()] = node
    return nodes


def source_to_key(nodes: dict[str, Node]) -> dict[str, str]:
    """Map each source file (and each folder) to the key of its page."""
    out = {}
    for node in nodes.values():
        if node.source:
            out[node.source] = node.key
        if node.is_folder:
            out[node.key] = node.key
    return out
