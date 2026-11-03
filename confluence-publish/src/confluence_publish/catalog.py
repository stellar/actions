"""Turn an incident.io service catalog (a services.auto.tfvars file) into docs.

The catalog is a Terraform variables file with one `services` map, keyed by
each service's external ID:

    services = {
      "account-viewer" = {
        name         = "Account Viewer"
        github_repos = ["stellar/account-viewer-v2"]
        owning_team  = "wallet-eng"
        urls         = ["https://accountviewer.stellar.org"]
      }
    }

It becomes a folder of Markdown that the publisher publishes like any other:

    services/README.md            -> "Services", listing every service page
    services/<external-id>.md     -> one page per service
    teams/README.md               -> "Teams", listing every team page
    teams/<team-id>.md            -> one page per distinct owning_team

(IDs become file names with anything but letters, digits, '.', '_' and '-'
turned into '-': 'hubspot-(crm)' -> 'hubspot-crm.md'.)

Pages are named by ID, so renaming a service keeps its page. Changing a
service's ID keeps it too, as long as its name doesn't change in the same run:
the publisher reuses a page whose file is gone for a new file with its title.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import hcl2

TEAM_SUFFIX = " (Team)"  # keeps team titles apart from service and other pages
ACRONYMS = {"ai", "api", "it", "sre", "ui"}
UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def file_name(identifier: str) -> str:
    """A stable file name for an ID: 'hubspot-(crm)' -> 'hubspot-crm'."""
    name = re.sub(r"-{2,}", "-", UNSAFE.sub("-", identifier)).strip("-.")
    if not name:
        raise ValueError(f"can't make a file name from the ID {identifier!r}")
    return name


def _str(value) -> str | None:
    """python-hcl2 keeps the quotes on strings: '"Account Viewer"'."""
    if value is None:
        return None
    value = str(value)
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return json.loads(value)
    return value


def load_services(path: Path) -> dict[str, dict]:
    """The catalog's services by external ID, with plain values."""
    with path.open() as f:
        data = hcl2.load(f)
    services = data.get("services")
    if isinstance(services, list):  # older python-hcl2 versions wrap blocks in lists
        services = services[0] if services else {}
    if not isinstance(services, dict) or not services:
        raise ValueError(f"{path}: no `services` map found")
    out = {}
    for key, fields in services.items():
        key = _str(key)
        team = _str(fields.get("owning_team"))
        out[key] = {
            "name": _str(fields.get("name")) or _str(key),
            "owning_team": team,
            "github_repos": [_str(r) for r in fields.get("github_repos") or []],
            "urls": [_str(u) for u in fields.get("urls") or []],
            "playbook": _str(fields.get("playbook")),
        }
    return out


def team_title(team_id: str) -> str:
    """'wallet-eng' -> 'Wallet Eng (Team)', 'sre-team' -> 'SRE (Team)'."""
    words = re.sub(r"[-_]team$", "", team_id).replace("_", "-").split("-")
    pretty = " ".join(w.upper() if w in ACRONYMS else w[:1].upper() + w[1:] for w in words if w)
    return pretty + TEAM_SUFFIX


def _front_matter(title: str) -> str:
    return f"---\ntitle: {json.dumps(title)}\n---\n\n"  # JSON strings are valid YAML


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def generate(catalog: Path, out: Path) -> None:
    """Write the docs folder for `catalog` into `out`, which must be empty or new."""
    services = load_services(catalog)
    teams = {s["owning_team"] for s in services.values() if s["owning_team"]}
    for kind, ids in (("service", services), ("team", teams)):
        seen: dict[str, str] = {}
        for i in sorted(ids):
            other = seen.setdefault(file_name(i), i)
            if other != i:
                raise ValueError(f"{catalog}: the {kind} IDs {other!r} and {i!r} would share "
                                 f"the page file {file_name(i)!r}; rename one")
    by_team: dict[str, list[str]] = defaultdict(list)
    for key, s in services.items():
        if s["owning_team"]:
            by_team[s["owning_team"]].append(key)

    (out / "services").mkdir(parents=True, exist_ok=True)
    (out / "teams").mkdir(parents=True, exist_ok=True)

    (out / "services" / "README.md").write_text(
        "# Services\n\nEvery service in the incident.io service catalog. Each page lists the "
        "service's owning team, repositories and links. Add a service's own docs as pages "
        "under its page, or publish them from its repository.\n")
    (out / "teams" / "README.md").write_text(
        "# Teams\n\nEvery team that owns a service in the incident.io service catalog, with "
        "the services it owns.\n")

    for key, s in sorted(services.items()):
        rows = []
        team = s["owning_team"]
        rows.append(("Owning team", f"[{_cell(team_title(team))}](../teams/{file_name(team)}.md)"
                     if team else "Not set in the catalog"))
        if s["github_repos"]:
            rows.append(("Repositories", ", ".join(
                f"[{_cell(r)}](https://github.com/{r})" for r in s["github_repos"])))
        if s["urls"]:
            rows.append(("Links", ", ".join(f"<{u}>" for u in s["urls"])))
        if s["playbook"]:
            rows.append(("Playbook", f"<{s['playbook']}>"))
        rows.append(("Catalog ID", f"`{key}`"))
        table = "| | |\n| --- | --- |\n" + "".join(f"| {k} | {v} |\n" for k, v in rows)
        (out / "services" / f"{file_name(key)}.md").write_text(
            _front_matter(s["name"]) + table +
            "\nThis page is generated from the service catalog. Put the service's docs in "
            "pages under this one, or publish them from its repository.\n")

    for team, keys in sorted(by_team.items()):
        items = "".join(f"- [{_cell(services[k]['name'])}](../services/{file_name(k)}.md)\n"
                        for k in sorted(keys, key=lambda k: services[k]["name"].lower()))
        (out / "teams" / f"{file_name(team)}.md").write_text(
            _front_matter(team_title(team)) + f"Services owned by `{team}`:\n\n" + items)
