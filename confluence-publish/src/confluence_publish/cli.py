"""confluence-publish: publish a folder of Markdown to Confluence Cloud.

Credentials come from the environment, never from flags:
  CONFLUENCE_BASE_URL   https://<site>.atlassian.net, or for a scoped or service
                        account token https://api.atlassian.com/ex/confluence/<cloud-id>
  CONFLUENCE_EMAIL      the account the token belongs to
  CONFLUENCE_API_TOKEN  the API token
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .client import Confluence, ConfluenceError
from .mermaid import MermaidRenderer
from .sync import publish, render_all
from .tree import TitleError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="confluence-publish", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("docs", type=Path, help="folder of Markdown to publish")
    p.add_argument("--root-page", help="id of the page to publish under; the folder's README.md "
                                       "becomes its content (see --adopt-root)")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                   help="owner/name; marks the pages this repo owns (default: $GITHUB_REPOSITORY)")
    p.add_argument("--branch", default="main", help="branch the 'edit in GitHub' links point at")
    p.add_argument("--github-url", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com"))
    p.add_argument("--on-orphan", choices=["keep", "delete"], default="keep",
                   help="what to do with a published page whose file is gone (delete = move to trash)")
    p.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    p.add_argument("--mermaid", action="store_true",
                   help="draw ```mermaid blocks as images with mermaid-cli; without it they "
                        "are shown as code")
    p.add_argument("--mermaid-command", default=os.environ.get("MERMAID_COMMAND", "mmdc"),
                   help="how to run mermaid-cli (default: mmdc, or $MERMAID_COMMAND)")
    p.add_argument("--mermaid-out-dir", type=Path,
                   default=Path(os.environ["MERMAID_OUT_DIR"]) if os.environ.get("MERMAID_OUT_DIR") else None,
                   help="where diagrams are written, e.g. a folder mounted into a mermaid-cli "
                        "container (default: $MERMAID_OUT_DIR, or a new temporary folder)")
    p.add_argument("--mermaid-puppeteer-config",
                   default=os.environ.get("MERMAID_PUPPETEER_CONFIG") or None,
                   help="Puppeteer config file for mermaid-cli, as mermaid-cli sees it (default: "
                        "$MERMAID_PUPPETEER_CONFIG, or one that only turns off Chrome's sandbox)")
    p.add_argument("--title-prefix", default=os.environ.get("CONFLUENCE_TITLE_PREFIX", ""),
                   help='put this in front of every page title, e.g. "Horizon: " '
                        "(default: $CONFLUENCE_TITLE_PREFIX)")
    p.add_argument("--adopt-root", action="store_true",
                   help="publish the folder's README.md into the root page even though it has "
                        "content this publisher did not write (only needed once)")
    p.add_argument("--editors-group-id", default=os.environ.get("CONFLUENCE_EDITORS_GROUP_ID", ""),
                   help="ID of the only Confluence group that may edit the pages the publisher "
                        "creates; the account must be in it (default: "
                        "$CONFLUENCE_EDITORS_GROUP_ID, or no restriction)")
    p.add_argument("--check", action="store_true",
                   help="only convert the docs and report problems; needs no credentials")
    a = p.parse_args(argv)

    if not a.docs.is_dir():
        p.error(f"{a.docs} is not a folder")
    blob = None
    if a.repo:
        rel = os.path.relpath(a.docs.resolve(), Path.cwd()).replace(os.sep, "/")
        rel = "" if rel == "." else "/" + rel
        blob = f"{a.github_url.rstrip('/')}/{a.repo}/blob/{a.branch}{rel}"

    try:
        mermaid = (MermaidRenderer(a.mermaid_command, a.mermaid_out_dir, a.mermaid_puppeteer_config)
                   if a.mermaid else None)
        if a.check:
            pages = render_all(a.docs, repo_blob_url=blob, mermaid=mermaid,
                               title_prefix=a.title_prefix)
            for key, r in pages.items():
                print(f"ok  {key}  ->  {r.node.title!r}" + (f"  (+{len(r.attachments)} attachments)" if r.attachments else ""))
            print(f"{len(pages)} pages convert cleanly")
            return 0

        missing = [n for n in ("CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN")
                   if not os.environ.get(n)]
        if missing:
            p.error("set " + ", ".join(missing) + " (or use --check)")
        if not a.root_page:
            p.error("--root-page is required to publish")
        if not a.repo:
            p.error("--repo is required outside GitHub Actions")
        client = Confluence(os.environ["CONFLUENCE_BASE_URL"], os.environ["CONFLUENCE_EMAIL"],
                            os.environ["CONFLUENCE_API_TOKEN"])
        publish(client, a.docs, root_page_id=a.root_page, repo=a.repo, repo_blob_url=blob,
                dry_run=a.dry_run, on_orphan=a.on_orphan, commit=os.environ.get("GITHUB_SHA", ""),
                mermaid=mermaid, title_prefix=a.title_prefix, adopt_root=a.adopt_root,
                editors_group_id=a.editors_group_id)
        return 0
    except (ValueError, ConfluenceError) as e:
        print(f"error: {e}", file=sys.stderr)
        if isinstance(e, TitleError) and os.environ.get("GITHUB_ACTIONS") == "true":
            # Shows the error on the file in GitHub: in the run summary and on the commit.
            path = os.path.relpath(a.docs / e.file).replace(os.sep, "/")
            print(f"::error file={_escape_property(path)},title=Confluence page title::"
                  f"{_escape(str(e))}")
        return 1
    except Exception as e:  # anything unexpected: a network error, a diagram timing out
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


def _escape(text: str) -> str:
    """Escape a message for a GitHub Actions workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    """Escape a workflow command property value (file=...), which also ends at ':' or ','."""
    return _escape(text).replace(":", "%3A").replace(",", "%2C")


if __name__ == "__main__":
    sys.exit(main())
