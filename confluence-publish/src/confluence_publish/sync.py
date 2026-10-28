"""Work out what to change in Confluence, then change it.

The publisher owns everything under its root page and nothing outside it.
Pages it publishes carry a content property (PROPERTY_KEY) naming the repo and
file; only those are updated, moved or trashed as the repo changes. Other pages
under the root are left alone, unless one has the same title as a doc, in
which case the doc is published into it. Pages outside the root are never
changed.

The root page is the one exception, and only for its content: the docs folder's
README.md is published into it when the root page is empty, already belongs to
this repo, or is adopted on purpose with adopt_root. It is never moved or
trashed.
"""

from __future__ import annotations

import re

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .convert import Context, heading_anchors, to_storage
from .tree import ROOT_KEY, Node, TitleError, build_tree

PROPERTY_KEY = "confluence-publish"
FORMAT_VERSION = 2  # bump to force every page to republish after a format change


@dataclass
class Rendered:
    node: Node
    body: str
    attachments: dict[str, Path]
    attachment_hashes: dict[str, str]
    hash: str


@dataclass
class Managed:
    id: str
    key: str
    title: str
    parent_id: str
    version: int
    prop: dict
    depth: int


@dataclass
class Step:
    action: str  # create | update | adopt | take-over | unchanged | delete | keep
    key: str
    title: str
    page_id: str | None = None
    reason: str = ""


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.action] = out.get(s.action, 0) + 1
        return out


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_all(docs: Path, *, repo_blob_url: str | None, mermaid=None,
               title_prefix: str = "", root_title: str | None = None) -> dict[str, Rendered]:
    nodes = build_tree(docs, title_prefix, root_title)
    titles = {}
    for n in nodes.values():
        if n.source:
            titles[n.source] = n.title
        if n.is_folder:
            titles[n.key] = n.title
    anchors = {}
    for n in nodes.values():
        found = heading_anchors(n.markdown)
        if n.source:
            anchors[n.source] = found
        if n.is_folder:
            anchors[n.key] = found
    out = {}
    for key, node in nodes.items():
        ctx = Context(source=node.source or f"{key}/README.md", docs_root=docs.resolve(),
                      titles_by_source=titles, repo_blob_url=repo_blob_url,
                      anchors_by_source=anchors, mermaid=mermaid)
        view = (f"{repo_blob_url.rstrip('/')}/{node.source or key}"
                if repo_blob_url else None)
        body = to_storage(node.markdown, ctx, view_url=view, is_folder=node.is_folder)
        att_hashes = {name: ctx.attachment_fingerprints.get(name) or _sha(p.read_bytes())
                      for name, p in sorted(ctx.attachments.items())}
        digest = _sha(json.dumps({"v": FORMAT_VERSION, "title": node.title, "parent": node.parent,
                                  "body": body, "attachments": att_hashes}, sort_keys=True).encode())
        out[key] = Rendered(node, body, dict(ctx.attachments), att_hashes, digest)
    return out


class Publisher:
    def __init__(self, client, *, root_page_id: str, repo: str, log=print):
        self.c = client
        self.root = root_page_id
        self.repo = repo  # e.g. "octocat/docs"; pages from another repo are left alone
        self.log = log

    # -- reading what is there ----------------------------------------------

    def discover(self) -> dict[str, Managed]:
        """Find the pages this repo published, anywhere under the root page.

        Also records every page under the root (self.subtree), so a doc whose title
        matches a page there can take that page over instead of failing.
        """
        found: dict[str, Managed] = {}
        self.subtree: dict[str, str] = {}  # page id -> parent id, for every page under the root
        stack = [(self.root, 0)]
        while stack:
            parent, depth = stack.pop()
            for child in self.c.child_pages(parent):
                stack.append((child["id"], depth + 1))
                self.subtree[child["id"]] = parent
                prop = self.c.get_property(child["id"], PROPERTY_KEY)
                if not prop or prop["value"].get("repo") != self.repo:
                    continue
                key = prop["value"]["key"]
                if key in found:  # two pages claim one file: keep the first, flag the other
                    key = f"{key}#duplicate-{child['id']}"
                page = self.c.get_page(child["id"])
                found[key] = Managed(child["id"], key, page["title"], parent,
                                     page["version"], prop, depth)
        return found

    def plan(self, rendered: dict[str, Rendered], managed: dict[str, Managed],
             space_id: str, on_orphan: str) -> Plan:
        plan = Plan()
        orphans = {k: m for k, m in managed.items() if k not in rendered}
        orphan_by_title = {m.title.lower(): m for m in orphans.values()}
        managed_by_title = {m.title.lower(): m for m in managed.values()}
        for key, r in rendered.items():
            if key == ROOT_KEY:
                continue  # planned by plan_root
            m = managed.get(key)
            if m:
                # Pages are updated one at a time, so a new title must be free before
                # the run starts (a swap would fail half way through).
                holder = managed_by_title.get(r.node.title.lower())
                if holder and holder.id != m.id:
                    raise TitleError(
                        f"{r.node.file} changes its title to {r.node.title!r}, which the page "
                        f"for {holder.key} still has. Swap or reuse titles in two commits.",
                        r.node.file)
                same = m.prop["value"].get("hash") == r.hash
                plan.steps.append(Step("unchanged" if same else "update", key, r.node.title, m.id))
                continue
            # A renamed or moved file keeps its title: reuse that page.
            o = orphan_by_title.pop(r.node.title.lower(), None)
            if o:
                orphans.pop(o.key, None)
                plan.steps.append(Step("adopt", key, r.node.title, o.id, f"was {o.key}"))
                continue
            existing = self.c.find_page_by_title(space_id, r.node.title)
            ours = {m.id: m.key for m in managed.values()}
            if existing in ours:
                raise TitleError(
                    f"{r.node.file} wants the title {r.node.title!r}, which the page for "
                    f"{ours[existing]} still has. Swap titles in two commits.", r.node.file)
            if existing and existing in getattr(self, "subtree", {}):
                # Everything under the root belongs to this repo: a page there with the
                # doc's title is published into, whoever made it.
                plan.steps.append(Step("take-over", key, r.node.title, existing,
                                       "same title, already under the root page"))
                continue
            if existing:
                prop = self.c.get_property(existing, PROPERTY_KEY)
                owner = (f"published by {prop['value'].get('repo')}" if prop
                         else "made by hand, not by this publisher")
                raise TitleError(
                    f"{r.node.file} would be published as {r.node.title!r}, but the space "
                    f"already has a page with that title ({owner}, page id {existing}), outside "
                    f"this repo's root page. Titles are unique per space, and this publisher "
                    f"never changes pages outside its root. To fix, {r.node.how_to_retitle()}.",
                    r.node.file)
            plan.steps.append(Step("create", key, r.node.title))
        # Trashing a page trashes the pages under it. Pages this run keeps are moved
        # out first; anything else under an orphan (made by hand, or another repo's)
        # means the orphan is kept instead.
        staying = {s.page_id for s in plan.steps if s.page_id}
        going = {o.id for o in orphans.values()}
        children: dict[str, list[str]] = {}
        for pid, parent in getattr(self, "subtree", {}).items():
            children.setdefault(parent, []).append(pid)

        def holds_others(pid: str) -> bool:
            return any(c not in staying and (c not in going or holds_others(c))
                       for c in children.get(pid, []))

        for o in sorted(orphans.values(), key=lambda m: -m.depth):
            if on_orphan != "delete":
                plan.steps.append(Step("keep", o.key, o.title, o.id, "source file is gone"))
            elif holds_others(o.id):
                plan.steps.append(Step("keep", o.key, o.title, o.id, "source file is gone, but "
                                       "it has pages under it that this repo did not publish"))
            else:
                plan.steps.append(Step("delete", o.key, o.title, o.id, "source file is gone"))
        return plan

    def plan_root(self, r: Rendered | None, root: dict, space_id: str,
                  adopt_root: bool) -> Step | None:
        """Decide whether the root page takes the docs folder's README.md."""
        if r is None:
            return None  # no README.md at the top: the root page is left alone
        prop = self.c.get_property(self.root, PROPERTY_KEY)
        owner = (prop or {}).get("value", {}).get("repo")
        if owner and owner != self.repo:
            raise TitleError(
                f"{r.node.file} would be published into the root page (id {self.root}), but "
                f"{owner} already publishes into it. Point this repo at another root page.",
                r.node.file)
        if r.node.title != root["title"]:
            existing = self.c.find_page_by_title(space_id, r.node.title)
            if existing and existing != self.root:
                raise TitleError(
                    f"{r.node.file} renames the root page to {r.node.title!r}, but the space "
                    f"already has a page with that title (page id {existing}). To fix, "
                    f"{r.node.how_to_retitle()}.", r.node.file)
        if owner:
            same = prop["value"].get("hash") == r.hash
            return Step("unchanged" if same else "update-root", ROOT_KEY, r.node.title, self.root)
        if _is_blank(self.c.get_page_body(self.root)):
            return Step("claim-root", ROOT_KEY, r.node.title, self.root, "root page is empty")
        if adopt_root:
            return Step("adopt-root", ROOT_KEY, r.node.title, self.root,
                        "replacing its hand-written content, as asked")
        raise TitleError(
            f"{r.node.file} would replace the content of the root page {root['title']!r} "
            f"(id {self.root}), which has content this publisher did not write. To publish "
            "into it anyway, run once with --adopt-root (the workflow's adopt_root input); "
            "after that the page belongs to this repo. To leave it alone, remove "
            f"{r.node.file}.", r.node.file)

    # -- changing things ----------------------------------------------------

    def apply_root(self, step: Step | None, r: Rendered | None, root: dict, *,
                   commit: str) -> None:
        if not step:
            return
        prop = self.c.get_property(self.root, PROPERTY_KEY)
        if step.action == "unchanged":
            # Content is current; still put back images removed or damaged since.
            if r.attachments:
                self._sync_attachments(self.root, r, prop["value"].get("attachments", {}))
            return
        self.c.update_page(self.root, title=r.node.title, parent_id=None, body=r.body,
                           version=root["version"],
                           message=f"Published from {self.repo}" + (f"@{commit[:12]}" if commit else ""))
        self.log(f"{step.action:9}{ROOT_KEY} -> root page {self.root}")
        self._sync_attachments(self.root, r, (prop or {}).get("value", {}).get("attachments", {}))
        self.c.set_property(self.root, PROPERTY_KEY, {
            "repo": self.repo, "key": ROOT_KEY, "hash": r.hash,
            "attachments": r.attachment_hashes, "commit": commit}, prop)


    def apply(self, plan: Plan, rendered: dict[str, Rendered], managed: dict[str, Managed],
              space_id: str, *, commit: str = "") -> None:
        ids: dict[str, str] = {}  # key -> page id, filled as pages are created
        by_id = {m.id: m for m in managed.values()}
        message = f"Published from {self.repo}" + (f"@{commit[:12]}" if commit else "")

        for step in plan.steps:
            if (step.action not in ("create", "update", "adopt", "unchanged", "take-over")
                    or step.key == ROOT_KEY):
                continue
            r = rendered[step.key]
            parent_id = ids[r.node.parent] if r.node.parent else self.root
            if step.action == "create":
                pid = self.c.create_page(space_id, parent_id, r.node.title, r.body)
                # Claim the page at once, with no hash: if the run dies before the end
                # of this step, the next run still knows the page is ours and redoes it.
                prop = self.c.set_property(pid, PROPERTY_KEY, {
                    "repo": self.repo, "key": step.key, "hash": "", "attachments": {},
                    "commit": commit}, None)
                self.log(f"created  {step.key} -> page {pid}")
            elif step.action == "take-over":
                pid = step.page_id
                page = self.c.get_page(pid)
                self.c.update_page(pid, title=r.node.title, parent_id=parent_id, body=r.body,
                                   version=page["version"], message=message)
                prop = self.c.get_property(pid, PROPERTY_KEY)  # may be another repo's marker
                self.log(f"took over {step.key} -> page {pid}")
            else:
                m = by_id[step.page_id]
                pid = m.id
                if step.action == "unchanged" and m.parent_id == parent_id:
                    ids[step.key] = pid
                    # Content is current; still put back images removed or damaged since.
                    if r.attachments:
                        self._sync_attachments(pid, r, m.prop["value"].get("attachments", {}))
                    continue
                self.c.update_page(pid, title=r.node.title, parent_id=parent_id, body=r.body,
                                   version=m.version, message=message)
                prop = m.prop
                self.log(f"{'moved   ' if step.action == 'unchanged' else step.action + ' ':9}{step.key} -> page {pid}")
            ids[step.key] = pid
            self._sync_attachments(pid, r, (prop or {}).get("value", {}).get("attachments", {}))
            # Written last, so a run that dies half way redoes this page next time.
            self.c.set_property(pid, PROPERTY_KEY, {
                "repo": self.repo, "key": step.key, "hash": r.hash,
                "attachments": r.attachment_hashes, "commit": commit}, prop)

        for step in plan.steps:
            if step.action == "delete":
                self.c.delete_page(step.page_id)
                self.log(f"deleted  {step.key} (page {step.page_id})")
            elif step.action == "keep":
                self.log(f"kept     {step.key} (page {step.page_id}): {step.reason}")

    def _sync_attachments(self, page_id: str, r: Rendered, old: dict[str, str]) -> None:
        if not r.attachments and not old:
            return
        current = self.c.attachments(page_id)
        for name, file in r.attachments.items():
            size = file.stat().st_size
            # Skip only when the recorded hash matches AND Confluence holds a file of
            # the right size, so an upload that went wrong is repaired next time.
            if (current.get(name, {}).get("size") == size
                    and old.get(name) == r.attachment_hashes[name]):
                continue
            stored = self.c.upload_attachment(page_id, name, file)
            if stored != size:
                raise ValueError(f"{r.node.key}: uploaded {name} ({size} bytes) but Confluence "
                                 f"recorded {stored} bytes")
            self.log(f"uploaded {name} ({size} bytes) to page {page_id}")
        # Images this tool uploaded before (named in the page's marker) that the doc
        # no longer uses go to the trash. Files people attached by hand are not in
        # the marker, so they are never touched.
        for name in sorted(set(old) - set(r.attachments)):
            if name in current:
                self.c.delete_attachment(current[name]["id"])
                self.log(f"trashed  {name} from page {page_id}: no longer used")


def _is_blank(storage: str) -> bool:
    """True for a page with no text, macros or images (a new, empty page)."""
    if re.search(r"<(ac:|ri:|img)", storage):
        return False
    return not re.sub(r"<[^>]+>|&nbsp;|\s", "", storage)


def publish(client, docs: Path, *, root_page_id: str, repo: str, repo_blob_url: str | None,
            dry_run: bool, on_orphan: str = "keep", commit: str = "", log=print,
            mermaid=None, title_prefix: str = "", adopt_root: bool = False) -> Plan:
    root = client.get_page(root_page_id)
    rendered = render_all(docs, repo_blob_url=repo_blob_url, mermaid=mermaid,
                          title_prefix=title_prefix, root_title=root["title"])
    pub = Publisher(client, root_page_id=root_page_id, repo=repo, log=log)
    managed = pub.discover()
    root_step = pub.plan_root(rendered.get(ROOT_KEY), root, root["spaceId"], adopt_root)
    plan = pub.plan(rendered, managed, root["spaceId"], on_orphan)
    if root_step:
        plan.steps.insert(0, root_step)
    for s in plan.steps:
        if s.action != "unchanged":
            log(f"plan: {s.action:9} {s.key}  ({s.title})" + (f"  [{s.reason}]" if s.reason else ""))
    log(f"plan summary: {plan.summary()}")
    if not dry_run:
        pub.apply_root(root_step, rendered.get(ROOT_KEY), root, commit=commit)
        pub.apply(plan, rendered, managed, root["spaceId"], commit=commit)
    return plan
