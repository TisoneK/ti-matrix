"""PyInstaller's entry point: a console program whose stdout is the handshake line.

The binary the desktop app bundles is this file frozen. It prints `TM1 <port> <token>` on stdout and
nothing else, which is the whole interface its parent needs.
"""
from appserver.main import main

if __name__ == "__main__":
    raise SystemExit(main())
