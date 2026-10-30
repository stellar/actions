import shutil
import xml.dom.minidom
from pathlib import Path

import pytest

from confluence_publish.tree import TitleError
from confluence_publish.sync import PROPERTY_KEY, publish, render_all
from fake import FakeConfluence

SAMPLE = Path(__file__).parent / "fixtures" / "docs"
REPO = "octo/docs"


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    shutil.copytree(SAMPLE, d)
    return d


def run(fake, docs, root, **kw):
    kw.setdefault("dry_run", False)
    return publish(fake, docs, root_page_id=root, repo=REPO,
                   repo_blob_url="https://github.com/octo/docs/blob/main/docs", log=lambda *_: None, **kw)


def live(fake):
    return {p["title"]: p for p in fake.pages.values() if not p["trashed"]}


def test_every_body_is_well_formed_xml(docs):
    for key, r in render_all(docs, repo_blob_url=None).items():
        wrapped = ('<root xmlns:ac="http://atlassian.com/content" '
                   'xmlns:ri="http://atlassian.com/resource/identifier">' + r.body + "</root>")
        xml.dom.minidom.parseString(wrapped)  # raises on bad XHTML


def test_conversion_details(docs):
    pages = render_all(docs, repo_blob_url="https://github.com/octo/docs/blob/main/docs")
    start = pages["getting-started.md"].body
    assert '<ri:page ri:content-title="Runbooks (docs-publisher test)" />' in start  # folder link
    assert 'ac:anchor="Install"' in start and "Setup guide (docs-publisher test)" in start
    assert 'ac:anchor="Run-the-tests"' in start  # multi-word heading
    assert '<ac:parameter ac:name="language">bash</ac:parameter>' in start
    assert "github.com/octo/docs/blob/main/docs/getting-started.md" in start  # banner link
    restart = pages["runbooks/restart.md"]
    assert '<ri:attachment ri:filename="diagram.png" />' in restart.body
    assert "&lt;b&gt;tag&lt;/b&gt;" in restart.body  # raw HTML is shown, not executed
    assert "diagram.png" in restart.attachments
    assert "Mermaid diagram" in pages["guides/setup.md"].body
    assert 'ac:name="children"' in pages["guides"].body  # folder pages list their children


def test_first_publish_builds_the_tree_and_never_edits_the_root(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page", body="hand written")
    run(fake, docs, root)
    pages = live(fake)
    assert pages["Parent page"]["version"] == 1 and pages["Parent page"]["body"] == "hand written"
    guides = pages["Guides"]
    assert guides["parentId"] == root
    assert pages["Setup guide (docs-publisher test)"]["parentId"] == guides["id"]
    assert pages["Restart the service (docs-publisher test)"]["parentId"] == pages["Runbooks (docs-publisher test)"]["id"]
    restart = pages["Restart the service (docs-publisher test)"]["id"]
    assert "diagram.png" in fake.files[restart]
    assert fake.props[(restart, PROPERTY_KEY)]["value"]["key"] == "runbooks/restart.md"


def test_second_run_with_no_changes_writes_nothing(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    fake.calls.clear()
    plan = run(fake, docs, root)
    assert fake.calls == []
    assert plan.summary() == {"unchanged": 5}


def test_edit_updates_in_place_and_keeps_the_page_id(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    before = live(fake)["Setup guide (docs-publisher test)"]["id"]
    (docs / "guides/setup.md").write_text(
        "# Setup guide (docs-publisher test)\n\nChanged.\n\n## Install\n\n## Run the tests\n")
    fake.calls.clear()
    run(fake, docs, root)
    assert fake.calls == [("update", before)]
    assert "Changed." in fake.pages[before]["body"]


def test_moving_a_file_moves_the_same_page(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    pid = live(fake)["Restart the service (docs-publisher test)"]["id"]
    (docs / "guides" / "img").mkdir()
    shutil.move(docs / "runbooks/img/diagram.png", docs / "guides/img/diagram.png")
    shutil.move(docs / "runbooks/restart.md", docs / "guides/restart.md")
    run(fake, docs, root, on_orphan="delete")
    page = fake.pages[pid]
    assert not page["trashed"] and page["parentId"] == live(fake)["Guides"]["id"]
    assert fake.props[(pid, PROPERTY_KEY)]["value"]["key"] == "guides/restart.md"


def test_removed_file_is_kept_by_default_and_trashed_on_request(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    pid = live(fake)["Setup guide (docs-publisher test)"]["id"]
    (docs / "guides/setup.md").unlink()
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n")
    run(fake, docs, root)
    assert not fake.pages[pid]["trashed"]
    run(fake, docs, root, on_orphan="delete")
    assert fake.pages[pid]["trashed"]


def test_refuses_a_title_clash_outside_the_root(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    elsewhere = fake.add("Guides", body="someone else's page")  # not under the root
    with pytest.raises(ValueError, match="made by hand") as e:
        run(fake, docs, root)
    assert fake.calls == []  # it failed while planning, before writing anything
    assert fake.pages[elsewhere]["body"] == "someone else's page"
    assert e.value.file == "guides"  # the folder, whose title came from its name
    assert "outside this repo's root page" in str(e.value)
    assert "rename the folder guides" in str(e.value)


def test_same_titled_page_under_the_root_is_refused(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    handmade = fake.add("Guides", parent=root, body="hand-written guides index")
    with pytest.raises(TitleError) as e:
        run(fake, docs, root)
    msg = str(e.value)
    assert "made by hand" in msg and handmade in msg and "under this repo's root page" in msg
    assert "rename or delete it in Confluence" in msg
    assert fake.pages[handmade]["body"] == "hand-written guides index"
    assert not [c for c in fake.calls if c[0] in ("create", "update", "delete")]


def test_same_titled_page_from_another_repo_under_the_root_is_refused(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    theirs = fake.add("Guides", parent=root, body="theirs")
    fake.props[(theirs, PROPERTY_KEY)] = {"id": "x", "version": 1,
                                          "value": {"repo": "other/repo", "key": "guides"}}
    with pytest.raises(TitleError) as e:
        run(fake, docs, root)
    assert "published by other/repo" in str(e.value)
    assert fake.pages[theirs]["body"] == "theirs"
    assert fake.props[(theirs, PROPERTY_KEY)]["value"]["repo"] == "other/repo"


def test_unmatched_pages_under_the_root_are_left_alone(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    note = fake.add("Horizon design doc", parent=root, body="written by hand")
    run(fake, docs, root, on_orphan="delete")
    run(fake, docs, root, on_orphan="delete")
    assert fake.pages[note]["body"] == "written by hand" and not fake.pages[note]["trashed"]
    assert all(c[1] != note for c in fake.calls if len(c) > 1)


def test_pages_from_another_repo_are_left_alone(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    other = fake.add("Other repo page", parent=root)
    fake.props[(other, PROPERTY_KEY)] = {"id": "x", "version": 1,
                                         "value": {"repo": "someone/else", "key": "a.md"}}
    run(fake, docs, root, on_orphan="delete")
    assert not fake.pages[other]["trashed"]


def test_dry_run_changes_nothing(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    plan = run(fake, docs, root, dry_run=True)
    assert fake.calls == [] and plan.summary() == {"create": 5}


def test_duplicate_titles_in_the_docs_are_rejected(docs):
    (docs / "guides/copy.md").write_text("# Setup guide (docs-publisher test)\n")
    with pytest.raises(ValueError, match="both be titled") as e:
        render_all(docs, repo_blob_url=None)


def test_broken_relative_link_is_an_error(docs):
    (docs / "guides/bad.md").write_text("# Bad page\n\n[x](missing.md)\n")
    with pytest.raises(ValueError, match="not in the docs"):
        render_all(docs, repo_blob_url=None)


def test_heading_anchors_match_confluence():
    from confluence_publish.convert import heading_anchors
    md = "## Run the tests\n\n## Step 2: `deploy`!\n\n## Run the tests\n"
    assert heading_anchors(md) == {
        "run-the-tests": "Run-the-tests",
        "step-2-deploy": "Step-2:-deploy!",
        "run-the-tests-1": "Run-the-tests",
    }


def test_unknown_anchor_is_passed_through(docs):
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n\n[x](guides/setup.md#nope)\n")
    body = render_all(docs, repo_blob_url=None)["getting-started.md"].body
    assert 'ac:anchor="nope"' in body


def _restart_page(fake):
    return live(fake)["Restart the service (docs-publisher test)"]["id"]


def _image(docs):
    return next(docs.rglob("diagram.png"))


def test_replacing_an_image_uploads_the_new_bytes(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    _image(docs).write_bytes(b"new image bytes")
    fake.calls.clear()
    run(fake, docs, root)
    pid = _restart_page(fake)
    assert ("upload", pid, "diagram.png") in fake.calls
    assert fake.files[pid]["diagram.png"] == b"new image bytes"


def test_a_failed_upload_stops_the_run_and_is_repaired_next_time(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    fake.break_uploads = True
    with pytest.raises(ValueError, match="recorded 0 bytes"):
        run(fake, docs, root)
    fake.break_uploads = False
    run(fake, docs, root)
    pid = _restart_page(fake)
    assert fake.files[pid]["diagram.png"] == _image(docs).read_bytes()


def test_an_empty_attachment_is_reuploaded_even_if_its_hash_was_recorded(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    pid = _restart_page(fake)
    fake.files[pid]["diagram.png"] = b""  # what the real site ended up holding
    (docs / "README.md").write_text("# Docs root\n")  # not published; nothing else changes
    md = next(docs.rglob("restart.md"))
    md.write_text(md.read_text() + "\nOne more line.\n")  # page changes, so it is revisited
    run(fake, docs, root)
    assert fake.files[pid]["diagram.png"] == _image(docs).read_bytes()


def test_an_image_removed_from_a_doc_is_trashed_but_hand_attached_files_stay(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    pid = _restart_page(fake)
    fake.files[pid]["notes.pdf"] = b"someone attached this by hand"
    md = next(docs.rglob("restart.md"))
    md.write_text(md.read_text().replace("![Architecture](img/diagram.png)", "No picture now."))
    fake.calls.clear()
    run(fake, docs, root)
    assert ("delete_attachment", pid, "diagram.png") in fake.calls
    assert set(fake.files[pid]) == {"notes.pdf"}
    fake.calls.clear()
    run(fake, docs, root)  # nothing left to clean up
    assert fake.calls == []


class FakeMermaid:
    """Stands in for mermaid-cli: writes a PNG-ish file whose bytes change every call,
    like a renderer whose output depends on the machine's fonts."""

    def __init__(self, out_dir):
        self.out_dir, self.calls = out_dir, 0
        out_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, source, where=""):
        from confluence_publish.mermaid import fingerprint
        self.calls += 1
        path = self.out_dir / f"mermaid-{fingerprint(source)[:16]}.png"
        # A real PNG header (1600 px wide), then bytes that change on every call.
        header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1600).to_bytes(4, "big")
        path.write_bytes(header + b"\x00" * 4 + str(self.calls).encode() * self.calls)
        return path


def test_mermaid_blocks_become_images(docs, tmp_path):
    pages = render_all(docs, repo_blob_url=None, mermaid=FakeMermaid(tmp_path))
    setup = pages["guides/setup.md"]
    [name] = [n for n in setup.attachments if n.startswith("mermaid-")]
    assert f'<ri:attachment ri:filename="{name}" />' in setup.body
    assert "graph TD" not in setup.body  # the source is not shown as code
    assert 'ac:width="760"' in setup.body  # 1600 px at 2x is 800, capped at 760


def test_redrawn_diagram_with_same_source_is_not_reuploaded(docs, tmp_path):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    publish(fake, docs, root_page_id=root, repo=REPO, repo_blob_url=None, dry_run=False,
            log=lambda *_: None, mermaid=FakeMermaid(tmp_path / "a"))
    fake.calls.clear()
    # A second run on another "machine" draws different bytes for the same diagram.
    plan = publish(fake, docs, root_page_id=root, repo=REPO, repo_blob_url=None, dry_run=False,
                   log=lambda *_: None, mermaid=FakeMermaid(tmp_path / "b"))
    assert plan.summary() == {"unchanged": 5} and fake.calls == []


def test_changing_a_diagram_uploads_a_new_image_and_trashes_the_old(docs, tmp_path):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    go = lambda: publish(fake, docs, root_page_id=root, repo=REPO, repo_blob_url=None,
                         dry_run=False, log=lambda *_: None, mermaid=FakeMermaid(tmp_path))
    go()
    pid = live(fake)["Setup guide (docs-publisher test)"]["id"]
    [old] = [n for n in fake.files[pid] if n.startswith("mermaid-")]
    md = docs / "guides/setup.md"
    md.write_text(md.read_text().replace("A-->B", "A-->C"))
    go()
    [new] = [n for n in fake.files[pid] if n.startswith("mermaid-")]
    assert new != old


def test_a_diagram_that_fails_to_render_stops_before_publishing(docs):
    def broken(source, where=""):
        raise ValueError("a Mermaid diagram failed to render:\n  Parse error on line 1")
    fake = FakeConfluence()
    root = fake.add("Parent page")
    with pytest.raises(ValueError, match="failed to render"):
        publish(fake, docs, root_page_id=root, repo=REPO, repo_blob_url=None, dry_run=False,
                log=lambda *_: None, mermaid=broken)
    assert fake.calls == []


def test_title_prefix_goes_on_every_page_and_into_links(docs):
    pages = render_all(docs, repo_blob_url=None, title_prefix="DP: ")
    assert {r.node.title for r in pages.values()} == {
        "DP: Guides", "DP: Setup guide (docs-publisher test)", "DP: Runbooks (docs-publisher test)",
        "DP: Restart the service (docs-publisher test)", "DP: Getting started (docs-publisher test)"}
    assert 'ri:content-title="DP: Setup guide (docs-publisher test)"' in pages["getting-started.md"].body


def test_adding_a_prefix_retitles_the_same_pages(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    before = {p["id"] for p in fake.pages.values() if not p["trashed"]}
    run(fake, docs, root, title_prefix="DP: ")
    after = live(fake)
    assert {p["id"] for p in after.values()} == before
    assert "DP: Guides" in after and "Guides" not in after


def test_prefix_lets_two_repos_share_a_title(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    publish(fake, docs, root_page_id=root, repo="octo/one", repo_blob_url=None, dry_run=False,
            log=lambda *_: None, title_prefix="One: ")
    publish(fake, docs, root_page_id=root, repo="octo/two", repo_blob_url=None, dry_run=False,
            log=lambda *_: None, title_prefix="Two: ")
    assert {"One: Guides", "Two: Guides"} <= set(live(fake))


def test_clash_with_another_repo_names_that_repo_and_what_to_change(docs):
    fake = FakeConfluence()
    other_root = fake.add("Other repo's root")
    root = fake.add("Parent page")
    publish(fake, docs, root_page_id=other_root, repo="octo/other", repo_blob_url=None,
            dry_run=False, log=lambda *_: None)
    with pytest.raises(ValueError) as e:
        run(fake, docs, root)
    msg = str(e.value)
    assert "published by octo/other" in msg
    assert "rename the folder guides" in msg  # guides/ is the first page planned


def test_clash_message_matches_where_the_title_came_from(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    fake.add("Getting started (docs-publisher test)")  # hand-made, outside the root
    with pytest.raises(ValueError) as e:
        run(fake, docs, root)
    assert e.value.file == "getting-started.md"
    assert "change `title:` in the front matter of getting-started.md" in str(e.value)


def test_cli_marks_the_file_in_github_actions(docs, monkeypatch, capsys):
    from confluence_publish.cli import main
    (docs / "guides/copy.md").write_text("# Setup guide (docs-publisher test)\n")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.chdir(docs.parent)
    assert main(["docs", "--check"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("::error file=docs/guides/")
    assert "title=Confluence page title::" in out


# -- the root page: README.md at the top of the docs folder ----------------------

ROOT_README = "# Ignored heading\n\nWelcome to the docs. See the [setup guide](guides/setup.md).\n"


def test_readme_fills_an_empty_root_page_and_keeps_its_title(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon")  # created by hand, still empty
    (docs / "README.md").write_text(ROOT_README)
    plan = run(fake, docs, root)
    page = fake.pages[root]
    assert plan.summary()["claim-root"] == 1
    assert page["title"] == "Horizon"  # a heading alone never renames the root
    assert "Welcome to the docs" in page["body"] and "Ignored heading" not in page["body"]
    assert 'ri:content-title="Setup guide (docs-publisher test)"' in page["body"]
    assert page["parentId"] is None  # never moved
    fake.calls.clear()
    assert run(fake, docs, root).summary() == {"unchanged": 6}
    assert fake.calls == []


def test_root_with_hand_written_content_needs_adopt_root(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon", body="<p>Someone wrote this by hand.</p>")
    (docs / "README.md").write_text(ROOT_README)
    with pytest.raises(ValueError, match="--adopt-root"):
        run(fake, docs, root)
    assert fake.calls == [] and "by hand" in fake.pages[root]["body"]
    run(fake, docs, root, adopt_root=True)
    assert "Welcome to the docs" in fake.pages[root]["body"]
    (docs / "README.md").write_text(ROOT_README + "\nMore.\n")
    run(fake, docs, root)  # owned now: no flag needed
    assert "More." in fake.pages[root]["body"]


def test_root_owned_by_another_repo_is_refused(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon")
    fake.props[(root, PROPERTY_KEY)] = {"id": "x", "version": 1,
                                        "value": {"repo": "someone/else", "key": "."}}
    (docs / "README.md").write_text(ROOT_README)
    with pytest.raises(ValueError, match="someone/else already publishes into it"):
        run(fake, docs, root, adopt_root=True)


def test_front_matter_title_renames_the_root(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon")
    (docs / "README.md").write_text("---\ntitle: Horizon service\n---\nHello.\n")
    run(fake, docs, root)
    assert fake.pages[root]["title"] == "Horizon service"


def test_removing_readme_leaves_the_root_page_alone(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon")
    (docs / "README.md").write_text(ROOT_README)
    run(fake, docs, root, on_orphan="delete")
    body = fake.pages[root]["body"]
    (docs / "README.md").unlink()
    fake.calls.clear()
    run(fake, docs, root, on_orphan="delete")
    assert not fake.pages[root]["trashed"] and fake.pages[root]["body"] == body
    assert all(c[0] != "update" or c[1] != root for c in fake.calls)


def test_link_to_the_root_readme_points_at_the_root_page(docs):
    (docs / "README.md").write_text(ROOT_README)
    (docs / "guides/back.md").write_text("# Back link\n\n[home](../README.md) and [also](..)\n")
    pages = render_all(docs, repo_blob_url=None, root_title="Horizon")
    assert pages["guides/back.md"].body.count('ri:content-title="Horizon"') == 2


def test_an_image_outside_the_docs_folder_is_refused(docs):
    (docs.parent / "secret.png").write_bytes(b"not for confluence")
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n\n![x](../secret.png)\n")
    with pytest.raises(ValueError, match="outside the docs folder"):
        render_all(docs, repo_blob_url=None)
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n\n![x](link.png)\n")
    (docs / "link.png").symlink_to(docs.parent / "secret.png")
    with pytest.raises(ValueError, match="outside the docs folder"):
        render_all(docs, repo_blob_url=None)


def test_a_title_swap_fails_before_changing_anything(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    (docs / "guides/setup.md").write_text("# Restart the service (docs-publisher test)\n")
    (docs / "runbooks/restart.md").write_text("# Setup guide (docs-publisher test)\n")
    fake.calls.clear()
    with pytest.raises(ValueError, match="two commits") as e:
        run(fake, docs, root)
    assert fake.calls == []
    assert e.value.file in ("guides/setup.md", "runbooks/restart.md")


def test_an_orphan_with_hand_made_pages_under_it_is_kept(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    guides = live(fake)["Guides"]["id"]
    setup = live(fake)["Setup guide (docs-publisher test)"]["id"]
    note = fake.add("Hand-written notes", parent=setup)
    (docs / "guides/setup.md").unlink()
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n")
    plan = run(fake, docs, root, on_orphan="delete")
    kept = {s.page_id for s in plan.steps if s.action == "keep"}
    assert {guides, setup} <= kept  # the note is under both
    assert not any(fake.pages[p]["trashed"] for p in (guides, setup, note))


def test_an_orphan_whose_children_all_go_is_trashed(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    guides = live(fake)["Guides"]["id"]
    setup = live(fake)["Setup guide (docs-publisher test)"]["id"]
    shutil.rmtree(docs / "guides")
    (docs / "getting-started.md").write_text("# Getting started (docs-publisher test)\n")
    run(fake, docs, root, on_orphan="delete")
    assert fake.pages[guides]["trashed"] and fake.pages[setup]["trashed"]


def test_an_attachment_removed_by_hand_is_put_back_on_an_unchanged_page(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    pid = _restart_page(fake)
    del fake.files[pid]["diagram.png"]
    fake.calls.clear()
    assert run(fake, docs, root).summary() == {"unchanged": 5}
    assert fake.calls == [("upload", pid, "diagram.png")]


def test_an_attachment_removed_by_hand_is_put_back_on_an_unchanged_root(docs):
    fake = FakeConfluence()
    root = fake.add("Horizon")
    (docs / "README.md").write_text(ROOT_README + "\n![Architecture](runbooks/img/diagram.png)\n")
    (docs / "runbooks/restart.md").write_text("# Restart the service (docs-publisher test)\n")
    run(fake, docs, root)
    del fake.files[root]["diagram.png"]
    fake.calls.clear()
    run(fake, docs, root)
    assert fake.calls == [("upload", root, "diagram.png")]


def test_symlinks_out_of_the_docs_folder_are_refused(docs):
    (docs.parent / "outside.md").write_text("# Outside\n")
    (docs / "linked.md").symlink_to(docs.parent / "outside.md")
    with pytest.raises(ValueError, match="outside the docs folder"):
        render_all(docs, repo_blob_url=None)
    (docs / "linked.md").unlink()
    (docs / "loop").symlink_to(docs, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked folders"):
        render_all(docs, repo_blob_url=None)


def test_a_symlink_inside_the_docs_folder_is_fine(docs):
    (docs / "runbooks/img/alias.png").symlink_to(docs / "runbooks/img/diagram.png")
    (docs / "runbooks/restart.md").write_text(
        "# Restart the service (docs-publisher test)\n\n![Same diagram](img/alias.png)\n")
    r = render_all(docs, repo_blob_url=None)["runbooks/restart.md"]
    assert "alias.png" in r.attachments


def test_a_symlinked_docs_folder_is_refused(docs, tmp_path):
    (tmp_path / "docs-link").symlink_to(docs, target_is_directory=True)
    with pytest.raises(ValueError, match="docs folder is a symlink"):
        render_all(tmp_path / "docs-link", repo_blob_url=None)


def test_created_pages_are_restricted_to_the_editors_group_id(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    handmade = fake.add("Notes", parent=root, body="hand-written")
    run(fake, docs, root, editors_group_id="g-1")
    pages = live(fake)
    created = [p for p in pages.values() if p["id"] not in (root, handmade)]
    assert created and all(p.get("editors") == "g-1" for p in created)
    # The root page and pages it didn't create keep their own permissions.
    assert "editors" not in fake.pages[root] and "editors" not in fake.pages[handmade]
    fake.calls.clear()
    run(fake, docs, root, editors_group_id="g-1")
    assert not [c for c in fake.calls if c[0] == "restrict"]  # nothing to redo


def test_no_editors_group_id_restricts_nothing(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    assert not [c for c in fake.calls if c[0] == "restrict"]


def test_a_refused_restriction_warns_and_is_retried_once_allowed(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    logs = []
    fake.break_restrictions = True
    publish(fake, docs, root_page_id=root, repo=REPO, dry_run=False, editors_group_id="g-1",
            repo_blob_url="https://github.com/octo/docs/blob/main/docs", log=logs.append)
    # The run finishes: every page is published, none restricted, one warning.
    assert len(live(fake)) == 6 and not any("editors" in p for p in live(fake).values())
    assert sum("::warning" in line for line in logs) == 1
    assert len([c for c in fake.calls if c[0] == "restrict"]) == 1  # gives up after one refusal
    # Once the account may restrict, the next run restricts the unchanged pages.
    fake.break_restrictions = False
    fake.calls.clear()
    assert run(fake, docs, root, editors_group_id="g-1").summary() == {"unchanged": 5}
    created = [p for p in live(fake).values() if p["id"] != root]
    assert all(p["editors"] == "g-1" for p in created)
    fake.calls.clear()
    run(fake, docs, root, editors_group_id="g-1")
    assert not [c for c in fake.calls if c[0] == "restrict"]


def test_turning_restrictions_on_later_restricts_existing_pages(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    run(fake, docs, root, editors_group_id="g-1")
    assert all(p.get("editors") == "g-1" for p in live(fake).values() if p["id"] != root)


def test_a_page_created_but_never_marked_is_reclaimed_next_run(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    fake.break_claims = 1  # the run dies right after creating its first page
    with pytest.raises(RuntimeError):
        run(fake, docs, root, editors_group_id="g-1")
    [stray] = [p for p in live(fake).values() if p["id"] != root]
    assert (stray["id"], PROPERTY_KEY) not in fake.props
    plan = run(fake, docs, root, editors_group_id="g-1")
    assert [s.action for s in plan.steps].count("reclaim") == 1
    assert len(live(fake)) == 6  # nothing duplicated
    mark = fake.props[(stray["id"], PROPERTY_KEY)]["value"]
    assert mark["repo"] == REPO and mark["created"] and mark["restricted"]
    assert fake.pages[stray["id"]]["editors"] == "g-1"


def test_a_lookalike_page_edited_since_is_refused(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    fake.break_claims = 1
    with pytest.raises(RuntimeError):
        run(fake, docs, root)
    [stray] = [p for p in live(fake).values() if p["id"] != root]
    fake.pages[stray["id"]]["version"] = 2  # someone edited it after the failed run
    with pytest.raises(TitleError, match="made by hand"):
        run(fake, docs, root)


def test_retitling_a_published_doc_onto_a_taken_title_fails_before_writing(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    elsewhere = fake.add("Elsewhere", body="someone else's")
    run(fake, docs, root)
    f = docs / "getting-started.md"
    f.write_text(f.read_text().replace("title: Getting started (docs-publisher test)",
                                       "title: Elsewhere", 1))
    fake.calls.clear()
    with pytest.raises(TitleError, match="made by hand") as e:
        run(fake, docs, root)
    assert e.value.file == "getting-started.md"
    assert not [c for c in fake.calls if c[0] in ("create", "update", "delete", "upload")]
    assert fake.pages[elsewhere]["body"] == "someone else's"


def _copy_with_marker(fake, title, new_title):
    """Copy a published page with its properties, as Confluence's "copy page" can."""
    src = live(fake)[title]
    copy = fake.add(new_title, parent=src["parentId"], body=src["body"])
    fake.props[(copy, PROPERTY_KEY)] = dict(fake.props[(src["id"], PROPERTY_KEY)])
    return src["id"], copy


def test_a_copied_page_claiming_the_same_file_is_kept_and_explained(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    original, copy = _copy_with_marker(fake, "Restart the service (docs-publisher test)",
                                       "Copy of Restart the service")
    logs = []
    plan = publish(fake, docs, root_page_id=root, repo=REPO, dry_run=False, on_orphan="delete",
                   repo_blob_url="https://github.com/octo/docs/blob/main/docs", log=logs.append)
    [keep] = [s for s in plan.steps if s.page_id in (original, copy) and s.action == "keep"]
    assert "probably a copy" in keep.reason and "runbooks/restart.md" in keep.reason
    assert not fake.pages[original]["trashed"] and not fake.pages[copy]["trashed"]


def test_a_copy_under_a_removed_folder_keeps_the_folder_page(docs):
    fake = FakeConfluence()
    root = fake.add("Parent page")
    run(fake, docs, root)
    _, copy = _copy_with_marker(fake, "Restart the service (docs-publisher test)",
                                "Copy of Restart the service")
    shutil.rmtree(docs / "runbooks")
    run(fake, docs, root, on_orphan="delete")
    folder = live(fake).get("Runbooks (docs-publisher test)")
    assert folder and not fake.pages[copy]["trashed"]


def test_a_folder_with_both_readme_and_index_is_refused(docs):
    (docs / "runbooks" / "index.md").write_text("# Runbooks index\n")
    with pytest.raises(TitleError, match="both README.md and index.md") as e:
        render_all(docs, repo_blob_url=None)
    assert e.value.file == "runbooks/index.md"


@pytest.mark.parametrize("title, match", [('"   "', "empty title"),
                                          ("x" * 256, "Confluence allows 255")])
def test_a_blank_or_overlong_title_fails_before_publishing(docs, title, match):
    f = docs / "getting-started.md"
    f.write_text(f.read_text().replace("title: Getting started (docs-publisher test)",
                                       f"title: {title}", 1))
    fake = FakeConfluence()
    root = fake.add("Parent page")
    with pytest.raises(TitleError, match=match) as e:
        run(fake, docs, root)
    assert e.value.file == "getting-started.md" and fake.calls == []


def test_a_title_prefix_counts_toward_the_limit(docs):
    f = docs / "getting-started.md"
    f.write_text(f.read_text().replace("title: Getting started (docs-publisher test)",
                                       "title: " + "x" * 250, 1))
    with pytest.raises(TitleError, match="Confluence allows 255"):
        render_all(docs, repo_blob_url=None, title_prefix="Horizon: ")


@pytest.mark.parametrize("md, linked", [
    ("See https://example.com/x?y=1 for more.", '<a href="https://example.com/x?y=1">'),
    ("Mail sre@example.org", '<a href="mailto:sre@example.org">'),
])
def test_bare_urls_become_links(md, linked):
    from confluence_publish.convert import Context, to_storage
    ctx = Context(source="a.md", docs_root=SAMPLE.resolve(), titles_by_source={})
    assert linked in to_storage(md, ctx, view_url=None, is_folder=False)


@pytest.mark.parametrize("md", ["Edit README.md and setup.py", "`https://in.code`",
                                "example.com"])
def test_file_names_code_and_bare_domains_are_not_linked(md):
    from confluence_publish.convert import Context, to_storage
    ctx = Context(source="a.md", docs_root=SAMPLE.resolve(), titles_by_source={})
    body = to_storage(md, ctx, view_url=None, is_folder=False)
    assert "<a " not in body.split("</ac:structured-macro>", 1)[1]


def test_a_title_with_a_line_break_is_refused(docs):
    (docs / "evil.md").write_text('---\ntitle: "Fine\\n::warning::injected"\n---\nbody\n')
    with pytest.raises(TitleError, match="line break or other control character"):
        render_all(docs, repo_blob_url=None)


def test_cli_turns_unexpected_errors_into_one_line(docs, monkeypatch, capsys):
    from confluence_publish import cli
    def boom(*a, **kw):
        raise ConnectionError("network unreachable")
    monkeypatch.setattr(cli, "render_all", boom)
    monkeypatch.chdir(docs.parent)
    assert cli.main(["docs", "--check"]) == 1
    assert capsys.readouterr().err == "error: ConnectionError: network unreachable\n"


def test_annotation_file_names_are_escaped():
    from confluence_publish.cli import _escape_property
    assert _escape_property("a,b:c%d\ne.md") == "a%2Cb%3Ac%25d%0Ae.md"


def test_a_link_to_a_repo_file_outside_the_docs_points_at_github(tmp_path):
    from confluence_publish.convert import Context, to_storage
    docs = tmp_path / "repo" / "docs"
    docs.mkdir(parents=True)
    (tmp_path / "repo" / "action.yml").write_text("name: x\n")
    ctx = Context(source="a.md", docs_root=docs.resolve(), titles_by_source={},
                  repo_blob_url="https://github.com/o/r/blob/main/docs")
    body = to_storage("[the action](../action.yml)", ctx, view_url=None, is_folder=False)
    assert '<a href="https://github.com/o/r/blob/main/action.yml">' in body
