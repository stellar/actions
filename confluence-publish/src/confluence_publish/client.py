"""A small Confluence Cloud REST client: only the calls the publisher needs.

The base URL is either the site (https://example.atlassian.net) or Atlassian's
gateway (https://api.atlassian.com/ex/confluence/<cloud-id>). Scoped API
tokens, including service account tokens, only work through the gateway.
Paths below start at /wiki, so both forms work.
"""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests


class ConfluenceError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _check_base_url(base: str) -> None:
    """Only ever send the token to Atlassian: the gateway or an atlassian.net site."""
    parts = urlsplit(base)
    host = (parts.hostname or "").lower()
    gateway = host == "api.atlassian.com" and parts.path.startswith("/ex/confluence/")
    site = host.endswith(".atlassian.net") and parts.path in ("", "/")
    if parts.scheme != "https" or parts.username or parts.port or not (gateway or site):
        raise ValueError(f"refusing Confluence base URL {base!r}: it must be "
                         "https://api.atlassian.com/ex/confluence/<cloud-id> or "
                         "https://<site>.atlassian.net, so the token only goes to Atlassian")


class Confluence:
    def __init__(self, base_url: str, email: str, token: str, *, retries: int = 5):
        self.base = base_url.rstrip("/")
        if self.base.endswith("/wiki"):
            self.base = self.base[: -len("/wiki")]
        _check_base_url(self.base)
        self.http = requests.Session()
        self.http.auth = (email, token)
        self.http.headers.update({"Accept": "application/json"})
        self.retries = retries

    # -- plumbing -----------------------------------------------------------

    def _call(self, method: str, path: str, **kw) -> requests.Response:
        if not path.startswith("/"):
            # Only ever our own base URL: the token must never go to a server-given host.
            raise ValueError(f"refusing to call {path!r}: not a path on the Confluence site")
        url = self.base + path
        for attempt in range(self.retries + 1):
            r = self.http.request(method, url, timeout=60, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < self.retries:
                    time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
                    continue
            if r.status_code >= 400:
                raise ConfluenceError(f"{method} {path} -> {r.status_code}: {r.text[:500]}",
                                      r.status_code)
            return r
        raise AssertionError("unreachable")

    def _json(self, method: str, path: str, **kw) -> dict:
        r = self._call(method, path, **kw)
        return r.json() if r.content else {}

    def _paged(self, path: str, params: dict | None = None):
        params = dict(params or {}, limit=250)
        data = self._json("GET", path, params=params)
        while True:
            yield from data.get("results", [])
            nxt = data.get("_links", {}).get("next")
            if not nxt:
                return
            # "next" is relative to the site; keep our base (site or gateway).
            data = self._json("GET", nxt if nxt.startswith("/wiki/") else "/wiki" + nxt)

    # -- pages --------------------------------------------------------------

    def get_page(self, page_id: str) -> dict:
        p = self._json("GET", f"/wiki/api/v2/pages/{page_id}")
        return {"id": p["id"], "title": p["title"], "parentId": p.get("parentId"),
                "spaceId": p["spaceId"], "version": p["version"]["number"]}

    def get_page_body(self, page_id: str) -> str:
        p = self._json("GET", f"/wiki/api/v2/pages/{page_id}", params={"body-format": "storage"})
        return p.get("body", {}).get("storage", {}).get("value", "")

    def child_pages(self, page_id: str) -> list[dict]:
        return [{"id": c["id"], "title": c["title"]}
                for c in self._paged(f"/wiki/api/v2/pages/{page_id}/children")]

    def find_page_by_title(self, space_id: str, title: str) -> str | None:
        for p in self._paged("/wiki/api/v2/pages", {"space-id": space_id, "title": title}):
            return p["id"]
        return None

    def create_page(self, space_id: str, parent_id: str, title: str, body: str) -> str:
        p = self._json("POST", "/wiki/api/v2/pages", json={
            "spaceId": space_id, "status": "current", "title": title, "parentId": parent_id,
            "body": {"representation": "storage", "value": body}})
        return p["id"]

    def update_page(self, page_id: str, *, title: str, parent_id: str | None, body: str,
                    version: int, message: str, attempts: int = 3) -> None:
        payload = {"id": page_id, "status": "current", "title": title,
                   "body": {"representation": "storage", "value": body}}
        if parent_id:  # None leaves the page where it is (used for the root page)
            payload["parentId"] = parent_id
        for attempt in range(1, attempts + 1):
            try:
                self._json("PUT", f"/wiki/api/v2/pages/{page_id}",
                           json={**payload, "version": {"number": version + 1, "message": message}})
                return
            except ConfluenceError as e:
                # 409: something else wrote the page meanwhile (seen as a transient
                # "unexpected row count" error on a real site). Re-read and try again.
                if e.status != 409 or attempt == attempts:
                    raise
                time.sleep(2 * attempt)
                version = self.get_page(page_id)["version"]

    def delete_page(self, page_id: str) -> None:
        self._call("DELETE", f"/wiki/api/v2/pages/{page_id}")  # moves it to the trash

    # -- restrictions (no v2 endpoint, so v1) ---------------------------------

    def restrict_edits(self, page_id: str, group_id: str) -> None:
        """Let only members of the group edit the page. Viewing is unchanged, and
        space admins can still lift the restriction. Takes the group's ID, not its
        name, so the token needs no group-reading scope."""
        self._call("PUT", f"/wiki/rest/api/content/{page_id}/restriction"
                          f"/byOperation/update/byGroupId/{group_id}")

    # -- content properties: where the publisher keeps its bookkeeping --------

    def get_property(self, page_id: str, key: str) -> dict | None:
        for prop in self._paged(f"/wiki/api/v2/pages/{page_id}/properties", {"key": key}):
            return {"id": prop["id"], "version": prop["version"]["number"], "value": prop["value"]}
        return None

    def set_property(self, page_id: str, key: str, value: dict, existing: dict | None) -> dict:
        """Create or update a property; returns it in the shape get_property uses."""
        if existing:
            p = self._json("PUT", f"/wiki/api/v2/pages/{page_id}/properties/{existing['id']}", json={
                "key": key, "value": value, "version": {"number": existing["version"] + 1}})
        else:
            p = self._json("POST", f"/wiki/api/v2/pages/{page_id}/properties",
                           json={"key": key, "value": value})
        return {"id": p["id"], "version": p["version"]["number"], "value": p["value"]}

    # -- attachments (uploading has no v2 endpoint yet, so it uses v1) --------

    def attachments(self, page_id: str) -> dict[str, dict]:
        """Each attachment by file name: {"id": ..., "size": bytes}."""
        return {a["title"]: {"id": a["id"], "size": a.get("fileSize", 0)}
                for a in self._paged(f"/wiki/api/v2/pages/{page_id}/attachments")}

    def delete_attachment(self, attachment_id: str) -> None:
        self._call("DELETE", f"/wiki/api/v2/attachments/{attachment_id}")  # moves it to the trash

    def upload_attachment(self, page_id: str, name: str, file: Path) -> int:
        """Create the attachment, or add a new version if the page has one by that name.

        Returns the size Confluence recorded. The file is read into memory first,
        so a retried request sends the whole file again, not an exhausted stream.
        """
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        data = file.read_bytes()
        r = self._json("PUT", f"/wiki/rest/api/content/{page_id}/child/attachment",
                       headers={"X-Atlassian-Token": "nocheck"},
                       files={"file": (name, data, mime)}, data={"minorEdit": "true"})
        result = (r.get("results") or [r])[0]
        return int(result.get("extensions", {}).get("fileSize", -1))
