"""Draw Mermaid diagrams as PNG images with mermaid-cli (mmdc).

Confluence Cloud does not draw Mermaid itself, so each ```mermaid block is
rendered to a PNG during publishing and uploaded as an attachment. The
diagram's source stays in Git.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

# Bump with the mermaid-cli version the workflow installs: it is part of each
# diagram's fingerprint, so a new renderer re-uploads every diagram once.
RENDERER_ID = "mermaid-cli@11.17.0"


def fingerprint(source: str) -> str:
    return hashlib.sha256(f"{RENDERER_ID}\n{source}".encode()).hexdigest()


class MermaidRenderer:
    """Callable: Mermaid source in, path to a PNG out. Same source, same file name."""

    def __init__(self, command: str = "mmdc", out_dir: Path | None = None):
        self.command = shlex.split(command)
        self.out_dir = out_dir or Path(tempfile.mkdtemp(prefix="mermaid-"))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # Chrome's sandbox does not start on GitHub's Ubuntu runners.
        self.puppeteer_config = self.out_dir / "puppeteer.json"
        self.puppeteer_config.write_text(json.dumps({"args": ["--no-sandbox"]}))

    def __call__(self, source: str) -> Path:
        name = f"mermaid-{fingerprint(source)[:16]}.png"
        out = self.out_dir / name
        if out.exists():
            return out
        src = self.out_dir / (name + ".mmd")
        src.write_text(source)
        try:
            subprocess.run([*self.command, "-i", str(src), "-o", str(out), "-b", "white",
                            "-s", "2", "-p", str(self.puppeteer_config)],
                           check=True, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            raise ValueError(f"cannot run {self.command[0]!r}: install @mermaid-js/mermaid-cli, "
                             "or publish without --mermaid") from None
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or "").strip().splitlines()[-5:]
            raise ValueError("a Mermaid diagram failed to render:\n  " + "\n  ".join(detail)) from None
        return out
