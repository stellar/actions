from confluence_publish import client as client_mod
from confluence_publish.client import Confluence, ConfluenceError


def test_update_retries_a_conflict_with_the_current_version(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    sent, versions = [], iter([7])
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(c, "get_page", lambda pid: {"version": next(versions)})

    def fake_json(method, path, **kw):
        sent.append(kw["json"]["version"]["number"])
        if len(sent) == 1:
            raise ConfluenceError("409 conflict", 409)
        return {}

    monkeypatch.setattr(c, "_json", fake_json)
    c.update_page("1", title="T", parent_id="2", body="b", version=5, message="m")
    assert sent == [6, 8]  # first try from the plan, retry from the re-read version


def test_update_does_not_retry_other_errors(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    calls = []

    def fake_json(method, path, **kw):
        calls.append(1)
        raise ConfluenceError("400 bad", 400)

    monkeypatch.setattr(c, "_json", fake_json)
    try:
        c.update_page("1", title="T", parent_id="2", body="b", version=5, message="m")
    except ConfluenceError as e:
        assert e.status == 400
    assert calls == [1]


def test_restrict_edits_looks_the_group_up_once(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    lookups, puts = [], []

    def paged(path, params=None):
        lookups.append((path, params))
        return iter([{"name": "publishers-old", "id": "g-0"}, {"name": "publishers", "id": "g-1"}])

    monkeypatch.setattr(c, "_paged", paged)
    monkeypatch.setattr(c, "_call", lambda m, path, **kw: puts.append((m, path)))
    c.restrict_edits("10", "publishers")
    c.restrict_edits("11", "publishers")
    assert lookups == [("/wiki/rest/api/group/picker", {"query": "publishers"})]
    assert puts == [("PUT", "/wiki/rest/api/content/10/restriction/byOperation/update/byGroupId/g-1"),
                    ("PUT", "/wiki/rest/api/content/11/restriction/byOperation/update/byGroupId/g-1")]


def test_restrict_edits_names_a_missing_group(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    monkeypatch.setattr(c, "_paged", lambda path, params=None: iter([{"name": "nope-2", "id": "x"}]))
    try:
        c.restrict_edits("10", "nope")
        raise AssertionError("expected an error")
    except ConfluenceError as e:
        assert "no Confluence group named 'nope'" in str(e)
