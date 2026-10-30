import re
import subprocess
from pathlib import Path

import pytest

from confluence_publish import mermaid
from confluence_publish.mermaid import RENDERER_ID, MermaidRenderer

ACTION = Path(__file__).parent.parent / "action.yml"


def test_renderer_id_matches_the_version_the_action_installs():
    installed = re.search(r"minlag/mermaid-cli:([\w.\-]+)@sha256:", ACTION.read_text()).group(1)
    assert RENDERER_ID == f"mermaid-cli@{installed}"


def test_the_renderer_gets_no_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "secret")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://example.invalid")
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw["env"])
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"png")

    monkeypatch.setattr(mermaid.subprocess, "run", fake_run)
    MermaidRenderer(out_dir=tmp_path)("graph TD; A-->B")
    assert seen["PATH"] == "/usr/bin"
    assert not [k for k in seen if k.startswith(("CONFLUENCE_", "AWS_", "ACTIONS_"))]
    assert "GITHUB_TOKEN" not in seen and "GH_TOKEN" not in seen


def test_a_diagram_that_hangs_names_the_doc(tmp_path, monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(mermaid.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match=r"runbook\.md: a Mermaid diagram took over 180 seconds"):
        MermaidRenderer(out_dir=tmp_path)("graph TD; A-->B", "runbook.md")
