"""Convert Markdown to Confluence storage format (XHTML with ac:/ri: macros)."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from .mermaid import fingerprint as mermaid_fingerprint

# Languages the Confluence code macro highlights. Anything else is shown plain.
CODE_LANGUAGES = {
    "actionscript3", "applescript", "bash", "c#", "cpp", "css", "coldfusion",
    "delphi", "diff", "erl", "groovy", "xml", "java", "jfx", "js", "php",
    "perl", "text", "powershell", "py", "ruby", "sql", "sass", "scala", "vb",
    "yml", "go", "kotlin", "rust", "swift", "typescript", "json",
}
LANGUAGE_ALIASES = {
    "sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash",
    "python": "py", "javascript": "js", "ts": "typescript", "yaml": "yml",
    "html": "xml", "hcl": "text", "terraform": "text", "csharp": "c#",
    "c++": "cpp", "rb": "ruby", "kt": "kotlin", "rs": "rust",
}


@dataclass
class Context:
    """What the converter needs to know about the page being converted."""

    source: str  # this file, relative to the docs root ("guides/setup.md")
    docs_root: Path
    titles_by_source: dict[str, str]  # source file or folder -> page title
    repo_blob_url: str | None = None  # e.g. https://github.com/o/r/blob/main/docs
    attachments: dict[str, Path] = field(default_factory=dict)  # name -> file
    # source file or folder -> {GitHub heading slug: Confluence heading anchor}
    anchors_by_source: dict[str, dict[str, str]] = field(default_factory=dict)
    # Draws a Mermaid diagram (source, doc it's in) and returns the PNG's path;
    # None shows the source as code.
    mermaid: Callable[[str, str], Path] | None = None
    # Attachment name -> fingerprint to use instead of hashing the file. Rendered
    # diagrams use their source, since the PNG's bytes vary with the runner's fonts.
    attachment_fingerprints: dict[str, str] = field(default_factory=dict)


def github_slug(text: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, spaces to '-'."""
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


def confluence_anchor(text: str) -> str:
    """The anchor Confluence Cloud's page view gives a heading: its text, spaces to '-'.

    Checked on a live site in October 2026: "Local Heading" became "Local-Heading".
    """
    return re.sub(r"\s+", "-", text.strip())


def heading_anchors(markdown: str) -> dict[str, str]:
    """Map each heading's GitHub slug to the anchor Confluence will give it."""
    out: dict[str, str] = {}
    tokens = MarkdownIt("commonmark").enable(["table", "strikethrough"]).parse(markdown)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            text = "".join(c.content for c in (tokens[i + 1].children or [])
                           if c.type in ("text", "code_inline"))
            slug = github_slug(text)
            n, key = 1, slug
            while key in out:  # GitHub numbers repeated headings: setup, setup-1, ...
                key, n = f"{slug}-{n}", n + 1
            out[key] = confluence_anchor(text)
    return out


def _png_width(path: Path) -> int:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG")
    return int.from_bytes(data[16:20], "big")


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _code_macro(code: str, info: str) -> str:
    lang = (info.split() or [""])[0].lower()
    params = ""
    if lang == "mermaid":
        params = ('<ac:parameter ac:name="language">text</ac:parameter>'
                  '<ac:parameter ac:name="title">Mermaid diagram</ac:parameter>')
    elif lang:
        lang = LANGUAGE_ALIASES.get(lang, lang)
        params = f'<ac:parameter ac:name="language">{escape(lang if lang in CODE_LANGUAGES else "text")}</ac:parameter>'
    return (f'<ac:structured-macro ac:name="code">{params}'
            f"<ac:plain-text-body>{_cdata(code.rstrip(chr(10)))}</ac:plain-text-body>"
            "</ac:structured-macro>\n")


def _is_relative(url: str) -> bool:
    parts = urlsplit(url)
    return not parts.scheme and not parts.netloc and not url.startswith("/")


def _resolve(ctx: Context, url: str) -> tuple[str, str]:
    """Return (path relative to the docs root, fragment) for a relative URL."""
    parts = urlsplit(url)
    base = posixpath.dirname(ctx.source)
    path = posixpath.normpath(posixpath.join(base, unquote(parts.path))) if parts.path else ctx.source
    return path.rstrip("/"), parts.fragment


def make_renderer(ctx: Context) -> MarkdownIt:
    # linkify: bare URLs become links, as on GitHub. Only ones with a scheme
    # (https://...) and email addresses: fuzzy matching would also link file names
    # such as README.md and setup.py, since .md and .py are real top-level domains.
    md = MarkdownIt("commonmark", {"xhtmlOut": True, "html": False, "linkify": True}).enable(
        ["table", "strikethrough", "linkify"])
    md.linkify.set({"fuzzy_link": False})
    rules = md.renderer.rules

    def fence(tokens, idx, options, env):
        tok = tokens[idx]
        if ctx.mermaid and (tok.info.split() or [""])[0].lower() == "mermaid":
            png = ctx.mermaid(tok.content, ctx.source)
            ctx.attachments[png.name] = png
            ctx.attachment_fingerprints[png.name] = mermaid_fingerprint(tok.content)
            # mermaid-cli draws at 2x for sharp text; show it at its natural size,
            # no wider than Confluence's default page width.
            width = min(_png_width(png) // 2, 760)
            return (f'<p><ac:image ac:alt="Mermaid diagram" ac:width="{width}">'
                    f'<ri:attachment ri:filename="{escape(png.name, quote=True)}" /></ac:image></p>\n')
        return _code_macro(tok.content, tok.info)

    def code_block(tokens, idx, options, env):
        return _code_macro(tokens[idx].content, "")

    def image(tokens, idx, options, env):
        tok = tokens[idx]
        src = tok.attrGet("src") or ""
        alt = escape(tok.content or "", quote=True)
        if _is_relative(src):
            path, _ = _resolve(ctx, src)
            file = (ctx.docs_root / path)
            # Only files in the docs folder are uploaded, never other repo files
            # reached through "../" or a symlink.
            if not file.resolve().is_relative_to(ctx.docs_root):
                raise ValueError(f"{ctx.source}: image {src!r} is outside the docs folder")
            if not file.is_file():
                raise ValueError(f"{ctx.source}: image {src!r} not found at {path}")
            name = file.name
            if name in ctx.attachments and ctx.attachments[name] != file:
                raise ValueError(f"{ctx.source}: two images named {name!r}; rename one")
            ctx.attachments[name] = file
            return f'<ac:image ac:alt="{alt}"><ri:attachment ri:filename="{escape(name, quote=True)}" /></ac:image>'
        return f'<ac:image ac:alt="{alt}"><ri:url ri:value="{escape(src, quote=True)}" /></ac:image>'

    def link_open(tokens, idx, options, env):
        tok = tokens[idx]
        href = tok.attrGet("href") or ""
        if not _is_relative(href):
            return f'<a href="{escape(href, quote=True)}">'
        path, fragment = _resolve(ctx, href)
        # Turn GitHub's "#setup-steps" into the heading anchor Confluence uses.
        fragment = ctx.anchors_by_source.get(path, {}).get(fragment.lower(), fragment)
        anchor = f' ac:anchor="{escape(fragment, quote=True)}"' if fragment else ""
        title = ctx.titles_by_source.get(path)
        if title is None and path.endswith((".md",)):
            raise ValueError(f"{ctx.source}: link {href!r} points to {path}, which is not in the docs")
        if title is not None:
            tok.meta["ac"] = True
            return (f'<ac:link{anchor}><ri:page ri:content-title="{escape(title, quote=True)}" />'
                    "<ac:link-body>")
        if path == ctx.source and fragment:  # link to a heading on this page
            tok.meta["ac"] = True
            return f"<ac:link{anchor}><ac:link-body>"
        if not (ctx.docs_root / path).exists():
            raise ValueError(f"{ctx.source}: link {href!r} points to {path}, which doesn't exist")
        if ctx.repo_blob_url:
            # A file elsewhere in the repo ("../action.yml"): link to it on GitHub,
            # with the ".." resolved so the link reads cleanly.
            url = urlsplit(ctx.repo_blob_url.rstrip("/") + "/" + path)
            url = url._replace(path=posixpath.normpath(url.path)).geturl()
            return f'<a href="{escape(url, quote=True)}">'
        return f'<a href="{escape(href, quote=True)}">'

    def link_close(tokens, idx, options, env):
        # Find the matching link_open to know which closing tag to write.
        depth = 0
        for j in range(idx - 1, -1, -1):
            t = tokens[j]
            if t.type == "link_close":
                depth += 1
            elif t.type == "link_open":
                if depth == 0:
                    return "</ac:link-body></ac:link>" if t.meta.get("ac") else "</a>"
                depth -= 1
        return "</a>"

    def softbreak(tokens, idx, options, env):
        # A line break inside a paragraph is a space in Markdown (as on GitHub).
        # Left as a newline, Confluence shows it as a hard line break.
        return " "

    def hardbreak(tokens, idx, options, env):
        return "<br />"  # without the newline after it, which would be a second break

    rules["softbreak"] = softbreak
    rules["hardbreak"] = hardbreak
    rules["fence"] = fence
    rules["code_block"] = code_block
    rules["image"] = image
    rules["link_open"] = link_open
    rules["link_close"] = link_close
    return md


def banner(view_url: str | None) -> str:
    if view_url:
        where = f'<a href="{escape(view_url, quote=True)}">its source file in GitHub</a>'
    else:
        where = "its source file in GitHub"
    return ('<ac:structured-macro ac:name="info"><ac:rich-text-body>'
            f"<p>This page is published from {where}. Edit it there: changes made here "
            "are overwritten the next time the docs are published.</p>"
            "</ac:rich-text-body></ac:structured-macro>\n")


CHILDREN_MACRO = ('<ac:structured-macro ac:name="children">'
                  '<ac:parameter ac:name="all">true</ac:parameter></ac:structured-macro>\n')


def to_storage(markdown: str, ctx: Context, *, view_url: str | None, is_folder: bool) -> str:
    """Render one page's body. Fills ctx.attachments with the images it uses."""
    md = make_renderer(ctx)
    body = md.render(markdown) if markdown.strip() else ""
    if is_folder:
        body += CHILDREN_MACRO
    return banner(view_url) + body
