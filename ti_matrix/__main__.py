"""The engine has no environment of its own, so `python -m ti_matrix` cannot run a goal by itself.

Run it through an adapter instead — the ones shipped here are host-free:

    python -m ti_matrix.adapters.files_cli "<goal>"                  # read-only local files
    python -m ti_matrix.adapters.ledger_cli --vault . "<goal>"       # a project's Context Ledger

A program that wants to drive the engine writes its own adapter (an ``Environment`` plus a ``ModelPort``) and
constructs ``StateEngine`` directly. This module imports nothing but the standard library.
"""
import sys

MESSAGE = (
    "ti_matrix is the engine, not a program: it needs an environment adapter to run.\n"
    "Shipped (host-free):  python -m ti_matrix.adapters.files_cli \"<goal>\"\n"
    "                      python -m ti_matrix.adapters.ledger_cli --vault . \"<goal>\"\n"
    "Your own program:     StateEngine(your_environment, proposer=..., evaluator=...).run(Goal(...))\n"
)


def main() -> int:
    print(MESSAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
