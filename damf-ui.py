"""Entry point for the DAMF Web UI and REST API server."""

from __future__ import annotations

import sys

from damf.cli import main as cli_main

if __name__ == "__main__":
    raise SystemExit(cli_main(["serve"] + sys.argv[1:]))
