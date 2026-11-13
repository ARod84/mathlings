# shared

Data that both apps read.

## game-topics.json

Which taxonomy topics each game practises, by level. Nothing here is shown to a child; it is for
the adaptive work to come.

- `_names` gives each topic id its name, so the file can be reviewed without the database. Tests
  check the names against the taxonomy.
- `number-pyramid.byLevel`: `addOnly` for levels where only the bottom row is given, `mixed` for
  levels with scattered givens, and `fourRows` added on top for any four-row level, whose top block
  goes past 20. `topicIdsForLevel` in `frontend/src/games/number-pyramid/pyramid.ts` applies that.
- `missing-number.byLevel`: one list per level, primary topic first. The backend decides the topics
  of each puzzle in `backend/app/puzzles/types/missing_number/levels.py`; a backend test fails if
  that file and this one disagree.
- `sequences.byLevel` ("Next in Line"): one list per level. At level 3 the topics of a step
  depend on the kind of sequence (through zero, or a growing step); the list is both kinds' topics,
  through-zero first. The backend decides in `backend/app/puzzles/types/sequences/levels.py`.
- Any other game the backend has a puzzle type for: the same shape, `byLevel` with one list per
  level number. A backend test compares every registered puzzle type's `levels` with its entry.

Who checks what:

| Check                                                      | Where                                 |
| ---------------------------------------------------------- | ------------------------------------- |
| Every id is a topic, with the name given in `_names`       | `backend/tests/test_game_topics.py`   |
| The same against the real imported database (slow)         | `backend/tests/test_game_topics.py`   |
| `levels.py` agrees with `missing-number`                   | `backend/tests/test_game_topics.py`   |
| Every registered puzzle type agrees with its entry         | `backend/tests/test_game_topics.py`   |
| Shape of the file; every game in the registry has an entry | `frontend/src/games/registry.test.ts` |
