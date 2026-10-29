"""An in-memory stand-in for the Confluence client, with Confluence's rules:
titles are unique per space and every update must bump the version by one."""

from __future__ import annotations

import itertools
from pathlib import Path


class FakeConfluence:
    def __init__(self, space_id: str = "S1"):
        self.space = space_id
        self.ids = itertools.count(1000)
        self.pages: dict[str, dict] = {}
        self.props: dict[tuple[str, str], dict] = {}
        self.files: dict[str, dict[str, bytes]] = {}
        self.calls: list[tuple] = []

    def add(self, title: str, parent: str | None = None, body: str = "") -> str:
        pid = str(next(self.ids))
        self._title_free(title)
        self.pages[pid] = {"id": pid, "title": title, "parentId": parent, "spaceId": self.space,
                           "version": 1, "body": body, "trashed": False}
        return pid

    def _title_free(self, title: str, except_id: str | None = None) -> None:
        for p in self.pages.values():
            if not p["trashed"] and p["title"].lower() == title.lower() and p["id"] != except_id:
                raise RuntimeError(f"title taken: {title}")

    # -- the client interface ------------------------------------------------

    def get_page(self, page_id):
        p = self.pages[page_id]
        return {k: p[k] for k in ("id", "title", "parentId", "spaceId", "version")}

    def get_page_body(self, page_id):
        return self.pages[page_id]["body"]

    def child_pages(self, page_id):
        return [{"id": p["id"], "title": p["title"]} for p in self.pages.values()
                if p["parentId"] == page_id and not p["trashed"]]

    def find_page_by_title(self, space_id, title):
        for p in self.pages.values():
            if not p["trashed"] and p["title"] == title:
                return p["id"]
        return None

    def create_page(self, space_id, parent_id, title, body):
        self.calls.append(("create", title))
        assert parent_id in self.pages
        return self.add(title, parent_id, body)

    def update_page(self, page_id, *, title, parent_id, body, version, message):
        self.calls.append(("update", page_id))
        p = self.pages[page_id]
        if version != p["version"]:
            raise RuntimeError("version conflict")
        self._title_free(title, page_id)
        p.update(title=title, body=body, version=version + 1)
        if parent_id:
            p["parentId"] = parent_id

    def delete_page(self, page_id):
        self.calls.append(("delete", page_id))
        self.pages[page_id]["trashed"] = True

    def get_property(self, page_id, key):
        return self.props.get((page_id, key))

    def set_property(self, page_id, key, value, existing):
        cur = self.props.get((page_id, key))
        if (cur is None) != (existing is None):
            raise RuntimeError("property create/update mismatch")
        version = (cur["version"] + 1) if cur else 1
        self.props[(page_id, key)] = {"id": f"p{page_id}", "version": version, "value": value}
        return dict(self.props[(page_id, key)])

    def attachments(self, page_id):
        return {name: {"id": f"att-{page_id}-{name}", "size": len(data)}
                for name, data in self.files.get(page_id, {}).items()}

    def delete_attachment(self, attachment_id):
        _, page_id, name = attachment_id.split("-", 2)
        self.calls.append(("delete_attachment", page_id, name))
        del self.files[page_id][name]

    # Set to True to make restricting a page fail, as if the account lacked the permission.
    break_restrictions = False

    def restrict_edits(self, page_id, group_id):
        self.calls.append(("restrict", page_id, group_id))
        if self.break_restrictions:
            raise RuntimeError("restriction refused")
        self.pages[page_id]["editors"] = group_id

    # Set to True to make uploads store an empty file, like the bug seen on a real site.
    break_uploads = False

    def upload_attachment(self, page_id, name, file: Path):
        self.calls.append(("upload", page_id, name))
        data = b"" if self.break_uploads else file.read_bytes()
        self.files.setdefault(page_id, {})[name] = data
        return len(data)
