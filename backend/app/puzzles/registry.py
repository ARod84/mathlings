"""Which puzzle types exist, by id prefix and by game name.

    registry = default_registry()
    registry.by_game("missing-number")     # the class; UnknownGame if there is none
    registry.by_code("mnc")                # for an id; None if no type has this prefix

Registering a class is all it takes for the generic routes, the service and
/players/me/next to serve it. The app gets its registry in create_app, so a
test can run the same app with one more type in it.
"""

from collections.abc import Iterable, Iterator

from app.puzzles.core import PuzzleType
from app.puzzles.types.missing_number import MissingNumberChains
from app.puzzles.types.sequences import NumberSequences
from app.puzzles.types.sum_grid import SumGrid


class UnknownGame(Exception):
    def __init__(self, game: str, games: list[str]) -> None:
        super().__init__(f"Unknown game: {game}")
        self.game = game
        self.games = games


class PuzzleRegistry:
    def __init__(self, types: Iterable[type[PuzzleType]] = ()) -> None:
        self._by_code: dict[str, type[PuzzleType]] = {}
        self._by_game: dict[str, type[PuzzleType]] = {}
        for puzzle_type in types:
            self.register(puzzle_type)

    def register(self, puzzle_type: type[PuzzleType]) -> None:
        code, game = puzzle_type.type_code, puzzle_type.game
        # An id is split on "-", so a code with one in it could never be read back.
        if not code.isalnum() or not code.islower():
            raise ValueError(f"type_code must be lower-case letters and digits: {code!r}")
        if code in self._by_code or game in self._by_game:
            raise ValueError(f"{game!r} ({code!r}) is already registered")
        self._by_code[code] = puzzle_type
        self._by_game[game] = puzzle_type

    @property
    def games(self) -> list[str]:
        """Every game, in the order registered."""
        return list(self._by_game)

    def by_game(self, game: str) -> type[PuzzleType]:
        try:
            return self._by_game[game]
        except KeyError:
            raise UnknownGame(game, self.games) from None

    def by_code(self, type_code: str) -> type[PuzzleType] | None:
        return self._by_code.get(type_code)

    def __iter__(self) -> Iterator[type[PuzzleType]]:
        return iter(self._by_game.values())

    def __len__(self) -> int:
        return len(self._by_game)


def default_registry() -> PuzzleRegistry:
    """The puzzle types the real app serves. Add a new type here."""
    return PuzzleRegistry([MissingNumberChains, NumberSequences, SumGrid])
