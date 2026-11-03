import shutil
from pathlib import Path

import pytest

from confluence_publish.catalog import file_name, generate, team_title
from confluence_publish.sync import PROPERTY_KEY, publish, render_all
from fake import FakeConfluence

CATALOG = Path(__file__).parent / "fixtures" / "catalog" / "services.auto.tfvars"
SOURCE = "https://github.com/octo/infra/blob/main/service-catalog/services.auto.tfvars"


@pytest.fixture
def docs(tmp_path):
    out = tmp_path / "catalog"
    generate(CATALOG, out)
    return out


def test_a_page_per_service_and_per_distinct_owning_team(docs):
    assert sorted(p.name for p in (docs / "services").iterdir()) == [
        "README.md", "account-viewer.md", "freighter.md", "hubspot-crm.md", "orphan-tool.md"]
    assert sorted(p.name for p in (docs / "teams").iterdir()) == [
        "README.md", "marketing.md", "wallet-eng.md"]
    wallet = (docs / "teams" / "wallet-eng.md").read_text()
    assert "[Account Viewer](../services/account-viewer.md)" in wallet
    assert "[Freighter](../services/freighter.md)" in wallet


def test_service_page_lists_team_repos_links_and_playbook(docs):
    page = (docs / "services" / "freighter.md").read_text()
    assert 'title: "Freighter"' in page
    assert "[Wallet Eng (Team)](../teams/wallet-eng.md)" in page
    assert "[stellar/freighter](https://github.com/stellar/freighter)" in page
    assert "<https://example.invalid/playbooks/freighter>" in page
    assert "`freighter`" in page
    assert "Not set in the catalog" in (docs / "services" / "orphan-tool.md").read_text()


def test_titles_and_file_names():
    assert team_title("wallet-eng") == "Wallet Eng (Team)"
    assert team_title("sre-team") == "SRE (Team)"
    assert team_title("it") == "IT (Team)"
    assert file_name("hubspot-(crm)") == "hubspot-crm"


def test_ids_sharing_a_file_name_are_refused(tmp_path):
    catalog = tmp_path / "services.auto.tfvars"
    catalog.write_text('services = {\n  "a-b" = { name = "One" }\n  "a(b)" = { name = "Two" }\n}\n')
    with pytest.raises(ValueError, match="would share the page file"):
        generate(catalog, tmp_path / "out")


def test_generated_pages_convert_and_point_at_the_catalog(docs):
    pages = render_all(docs, repo_blob_url=None, source_url=SOURCE,
                       generated_from="the service catalog in GitHub")
    assert len(pages) == 1 + 4 + 1 + 2  # the two index pages plus a page each
    body = pages["services/freighter.md"].body
    assert "This page is generated from" in body and SOURCE in body
    assert 'ri:content-title="Wallet Eng (Team)"' in body


def test_publishing_twice_changes_nothing_and_a_rename_keeps_the_page(docs, tmp_path):
    fake = FakeConfluence()
    root = fake.add("Redesign")
    run = lambda d: publish(fake, d, root_page_id=root, repo="octo/infra", repo_blob_url=None,
                            dry_run=False, on_orphan="delete", log=lambda *_: None,
                            source_url=SOURCE, generated_from="the service catalog in GitHub")
    run(docs)
    page = {p["title"]: p["id"] for p in fake.pages.values()}["Freighter"]
    fake.calls.clear()
    assert set(run(docs).summary()) == {"unchanged"}
    # Rename the service: same ID, same page.
    renamed = tmp_path / "renamed.auto.tfvars"
    renamed.write_text(CATALOG.read_text().replace('name         = "Freighter"', 'name         = "Freighter Wallet"'))
    out = tmp_path / "renamed"
    generate(renamed, out)
    run(out)
    assert fake.pages[page]["title"] == "Freighter Wallet" and not fake.pages[page]["trashed"]
    assert fake.props[(page, PROPERTY_KEY)]["value"]["key"] == "services/freighter.md"


def test_cli_checks_a_catalog(monkeypatch, capsys, tmp_path):
    from confluence_publish.cli import main
    shutil.copy(CATALOG, tmp_path / "services.auto.tfvars")
    monkeypatch.chdir(tmp_path)
    assert main(["--service-catalog", "services.auto.tfvars", "--check", "--repo", "octo/infra"]) == 0
    assert "8 pages convert cleanly" in capsys.readouterr().out


def test_cli_wants_a_folder_or_a_catalog_not_both(tmp_path, monkeypatch):
    from confluence_publish.cli import main
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    with pytest.raises(SystemExit):
        main(["docs", "--service-catalog", str(CATALOG), "--check"])
    with pytest.raises(SystemExit):
        main(["--check"])
