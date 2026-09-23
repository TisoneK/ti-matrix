"""`python -m appserver` — the same entry the packaged binary and the console script resolve to."""
from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
