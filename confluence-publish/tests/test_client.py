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


def test_restrict_edits_adds_the_group_to_the_edit_restriction(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    puts = []
    monkeypatch.setattr(c, "_call", lambda m, path, **kw: puts.append((m, path)))
    c.restrict_edits("10", "g-1")
    assert puts == [("PUT", "/wiki/rest/api/content/10/restriction/byOperation/update/byGroupId/g-1")]


def test_calls_only_go_to_the_configured_site(monkeypatch):
    c = Confluence("https://example.atlassian.net", "me@example.com", "token")
    monkeypatch.setattr(c.http, "request", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sent")))
    try:
        c._call("GET", "https://evil.example/wiki/x")
        raise AssertionError("expected a refusal")
    except ValueError as e:
        assert "not a path on the Confluence site" in str(e)
