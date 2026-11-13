"""Quality report for a puzzle type's generator.

    uv run python -m app.puzzles.report --game sequences --all --count 5000
    uv run python -m app.puzzles.report --game missing-number --level 1
    uv run python -m app.puzzles.report --game sequences --samples 2
    uv run python -m app.puzzles.report --game sequences --catalog

Each type measures what matters for it, so each has its own report module in
its folder. This is only the way in: it picks the module by game name and
hands it the rest of the command line. `--help` after a game shows that
game's options.
"""

import argparse
from collections.abc import Callable

from app.puzzles.types.missing_number import report as missing_number_report
from app.puzzles.types.missing_number.levels import GAME as MISSING_NUMBER
from app.puzzles.types.sequences import report as sequences_report
from app.puzzles.types.sequences.levels import GAME as SEQUENCES

# A new puzzle type adds its report here.
REPORTS: dict[str, Callable[[list[str] | None], int]] = {
    MISSING_NUMBER: missing_number_report.main,
    SEQUENCES: sequences_report.main,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], add_help=False)
    parser.add_argument("--game", choices=sorted(REPORTS), required=True)
    args, rest = parser.parse_known_args(argv)
    return REPORTS[args.game](rest)


if __name__ == "__main__":
    raise SystemExit(main())
