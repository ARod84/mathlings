# Mathlings

Short math-logic puzzle games for kids aged 7–12. This is a standalone precursor to the
Martians Space Club site and will be merged into it later, so its visual language comes from that
site's design.

This is the frontend: the design system, the `GameShell` that every game renders inside, a home
screen, and two games. Number Pyramid runs entirely in the browser. Missing Number Chains gets its
puzzles from the backend in `../backend`. Nothing is saved between visits.

## Getting started

```bash
npm install
npm run dev        # home screen at http://localhost:5173
```

| Script                 | What it does                                            |
| ---------------------- | ------------------------------------------------------- |
| `npm run dev`          | Vite dev server; proxies `/api` to port 8000            |
| `npm test`             | Vitest, single run                                      |
| `npm run test:watch`   | Vitest in watch mode                                    |
| `npm run lint`         | ESLint                                                  |
| `npm run typecheck`    | TypeScript (strict), no emit                            |
| `npm run format`       | Prettier, write                                         |
| `npm run format:check` | Prettier, check only                                    |
| `npm run build`        | Typecheck, then production build to `dist/`             |
| `npm run api:types`    | Regenerate `src/api/schema.d.ts` from `../openapi.json` |

Stack: Vite, React, TypeScript (strict), plain CSS with custom properties and CSS Modules, Vitest
with React Testing Library and MSW, `openapi-fetch` for the API, `lucide-react` icons, and fonts
self-hosted through `@fontsource/*`.

```
src/
  design/   tokens.css, tokens.ts, global.css, contrast helpers and their tests
  shell/    GameShell and its parts (progress, action bar, hint bubble, solved screen, sound hook)
  games/    registry.ts and one folder per game: number-pyramid/, missing-number/, sequences/,
            sum-grid/; usePuzzleSession.ts and session/ for what server-checked games share
  home/     the home screen: one card per game
  api/      the typed API client and the generated schema.d.ts
  test/     test setup, the MSW server and the pretend puzzle backend
  dev/      ShellDemo: the shell review page, at #shell-demo
  App.tsx   picks the screen for the current route
  router.ts the hash router
```

## Running with the backend

Missing Number Chains needs the API. Start the backend on port 8000 (see `../README.md`), then
`npm run dev`. `vite.config.ts` proxies `/api` to `http://localhost:8000`, so in development the
browser uses one origin. To point at an API somewhere else, set `VITE_API_BASE_URL`.

## Routes

`src/router.ts` is a small hash router with no library behind it. The part of the address after
`#` picks the screen, and changing it re-renders without reloading the page.

| Address            | Screen                       |
| ------------------ | ---------------------------- |
| `#/`               | Home (also any unknown hash) |
| `#/pyramid`        | Number Pyramid               |
| `#/missing-number` | Missing Number Chains        |
| `#/sequences`      | Next in Line                 |
| `#/sum-grid`       | Sum Grid                     |
| `#shell-demo`      | The GameShell review page    |

`useRoute()` returns the current route and `navigate(route)` changes it. The game routes are
built from `src/games/registry.ts`: an entry's `route` is its hash, `#/<route>`, and the `Route`
type is derived from the registry's entries. Only `home` and `shell-demo` are written in
`router.ts` itself, so adding a game needs no change there.

If a route does nothing in development after an edit (the address changes, the screen does not),
restart `npm run dev`. That happened once with a file written twice in quick succession: the dev
server kept serving the first version, and the code on disk and in the tests was right all along.

## Games registry and adding a game

`src/games/registry.ts` lists the games as `{ id, title, route, house, description }`. The home
screen draws one card per entry, and `App.tsx` passes each game its `house` from there.

To add a game:

1. Add an entry to `GAMES` in `src/games/registry.ts` (its `route` becomes the hash), and the
   game's topics to `../shared/game-topics.json` (a test fails if a registered game has none).
2. Create `src/games/<name>/` with the logic (pure functions, or a hook with a reducer), a
   component that renders inside `GameShell` and accepts `house` and `onExit`, and tests.
3. Render it for its route in `src/App.tsx`.

## How to add a puzzle type

For a game whose puzzles the backend makes and checks. Do the backend checklist first
(`../backend/README.md`, "How to add a puzzle type"); it ends with a new `openapi.json`. A game
that needs no server, like Number Pyramid, only needs the four steps above.

1. **Types.** Run `npm run api:types`. The game's request and public shapes are now in
   `src/api/schema.d.ts`.
2. **API shapes.** Add the game to `GameShapes` in `src/api/puzzles.ts`:
   `'<game>': { request: components['schemas'][...]; puzzle: components['schemas'][...] }`.
   `newPuzzle('<game>', ...)` and `usePuzzleSession` are typed from that entry. The check and hint
   calls need nothing.
3. **Topics.** The game's entry in `../shared/game-topics.json` was added on the backend side; the
   registry reads it.
4. **Registry.** Add an entry to `GAMES` in `src/games/registry.ts` (id, title, route, house,
   description, `topicIds`). Use the same id as the backend's game name. The route becomes the
   hash `#/<route>`; `src/router.ts` needs no change.
5. **Session config.** In `src/games/<name>/`, write the game's hook on `usePuzzleSession`, the
   way `missing-number/useMissingNumberGame.ts` does: a `PuzzleSessionConfig` (defined once,
   outside the component) with the game id, the round size, `asksBackend`, `fixedLevel`, `choose`
   (the level and request body for each puzzle, with a fallback for when `/next` has no answer)
   and `hintTiers`. Do not reimplement loading, checking, hints or error handling.
6. **Component.** Draw the puzzle from the session's state inside `GameShell`, passing
   `feedback`, `hint`, `onHint`, `onCheck`, `onReset` and `onNext` from the session. The component
   decides how an answer is picked and calls `select(value)`; an answer is a number. Nothing the
   server sends for adults (`reason`, `focus`, the diagnosis) may reach the page.
7. **Render it** for its route in `src/App.tsx`.
8. **Tests.** A fixture backend for the game in `src/test/` (see `puzzleBackend.ts`, typed from
   the schema so a change to the API breaks it at compile time), and tests for the component:
   a full round, a wrong answer, hints, the automatic hint, a 410, an error and retry. The
   session's own behaviour is already covered by `src/games/usePuzzleSession.test.tsx`.

## API client

| File                  | Role                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------ |
| `src/api/schema.d.ts` | Types generated from `../openapi.json`. Never edited by hand.                                          |
| `src/api/client.ts`   | The one configured `openapi-fetch` client.                                                             |
| `src/api/puzzles.ts`  | `newPuzzle(game, request)`, `getPuzzle`, `checkStep`, `getHint`, each returning a result; `GameShapes` |
| `src/api/player.ts`   | The anonymous player id (`getPlayerId`, `forgetPlayer`) and `getNextPuzzle(game)`                      |

Every function in `puzzles.ts` returns `{ status: 'ok', data }` or one of `notFound`, `gone`,
`unavailable`, `network`. Components branch on that name and never read an HTTP status code.

The puzzle routes are the same for every game (`POST /api/v1/puzzles/{game}`, then the puzzle id).
`GameShapes` in `puzzles.ts` names, per game, the request body and the puzzle that comes back, and
`newPuzzle` is typed from it. `newMissingNumber` is `newPuzzle('missing-number', ...)`. `sequences`
("Next in Line") is the second entry. `GAMES_WITHOUT_A_SCREEN` in `src/games/gameTopics.ts` lists
games the backend serves that have no screen here yet; it is empty now.

When the backend's API changes: export `openapi.json` there, then run `npm run api:types` here. A
test fails if `schema.d.ts` is out of date. `openapi-typescript` asks for TypeScript 5 as a peer;
the `overrides` entry in `package.json` lets it install alongside TypeScript 6, which it works with.

### The player id

`getPlayerId()` returns a random UUID kept in `localStorage` under `mathlings.playerId`, making it
on first call. A middleware in `client.ts` sends it as `X-Player-Id` on every puzzle request, and
the backend keeps practice history under it. It is a pseudonymous identifier, not a login; the
[root README](../README.md#privacy) has the privacy rules.

- If `localStorage` is unavailable (private mode, blocked storage), `getPlayerId()` returns `null`,
  no header is sent, nothing is stored, and the game plays as usual.
- `forgetPlayer()` calls `DELETE /api/v1/players/me` and then removes the key. If the delete fails
  the key is kept, so it can be tried again.
- The home screen footer has the "Forget my progress on this device" button, with a confirm step
  inside the page.

### Testing against the API

Tests never call a real server. `src/test/puzzleBackend.ts` is a pretend puzzle API on MSW whose
responses are typed from `schema.d.ts`, so a change to the API's shape breaks the fixtures at
compile time. A request no handler expects fails the test. `backend.playerIds` lists the
`X-Player-Id` header of every request. `src/test/setup.ts` gives each test an empty in-memory
`localStorage` (`src/test/storage.ts`), because Node 25 has a `localStorage` global of its own that
hides the one from jsdom.

Two rules that keep these tests steady, both learned from a flaky run (13 failures in 35 runs of
the suite, none in 35 after):

- **Wait for what lasts.** The games' tests pass a short `timing` (20 ms), so the "correct"
  feedback is over almost at once, and the answer often comes back while `user.click` is still
  being awaited. Wait for the next step or the solved screen, not for `data-feedback="correct"`.
  A test that is about that feedback passes a longer `timing` instead.
- **Whole-round tests use `userEvent.setup({ delay: null })`.** By default user-event waits on a
  zero-length timer between the events of a click. On Windows that timer takes about 12 ms, so a
  round of thirty clicks ran at 3 to 5 seconds against the 5 second limit.

## Missing Number Chains

`src/games/missing-number`: equations with one missing number, linked in a chain. A round is five
puzzles.

- **Start screen.** One big "Play" button, and under it a smaller row, "Or choose a range" (up
  to 20, 100 or 1000).
- **Play.** Before each puzzle of the round the game asks `GET /players/me/next` and uses the
  level and chain length it recommends, so the round adapts as the child plays. With no player
  id, or if the call fails, the puzzle is level 1 with 2 steps, and nothing is said about it.
  The reason, the mastery values and the focus rule are logged with `console.debug` in
  development and never reach the page.
- **Focus.** If `/next` returns a `focus` (a mistake to target), the game passes it unchanged
  in the new-puzzle request. When it is null the field is not sent. Nothing changes on screen,
  and the child is never told a puzzle is focused.
- **A chosen range.** Five puzzles at that level with 2, 2, 3, 3 and 4 steps; `/next` is not
  called.

- **One step at a time.** Solved steps stay above, faded, with their answer filled in. The current
  step is big, and later steps are not on the page. When a new step appears, the number just
  found is highlighted in it.
- **Answering.** Four option tiles; tapping one puts it in the box, tapping another swaps it.
  Keys 1 to 4 pick an option and Enter checks. The server checks every answer.
- **Wrong answers.** The box stays filled. After two wrong tries on a step, the next hint opens by
  itself, unless that would be the last tier: that one shows the answer, so the child has to ask.
- **Hints.** Each press fetches the next tier (1, 2, 3) for the current step; then the button is
  disabled. Reset empties the current box only.
- **Diagnosis.** What the server says about a wrong answer is kept in state and logged with
  `console.debug` in development. It is never shown to the child.
- **Problems.** A puzzle from an older generator version is replaced by a fresh one without a
  message. Anything else shows a friendly note with a Try again button, which repeats whatever
  failed. Leaving the game cancels requests in flight.

The start screen, the loading placeholder, the error message and the four answer tiles are the
shared ones in `src/games/session/` (`SessionScreens.tsx`, and `useOptionKeys.ts` for keys 1 to 4
and Enter); Next in Line uses the same.

The state (a reducer) and the API calls are in `src/games/usePuzzleSession.ts`, which any
server-checked game can use: loading, `/next` before each puzzle, check, hint tiers, the automatic
hint, the 410 restart, errors and cancelling. `useMissingNumberGame.ts` is a thin layer on top: it
gives the session a config (the game id, how a round picks level and chain length, how many hint
tiers a step has) and names the two ways to start a round. `MissingNumber.tsx` only draws. `equation.ts` turns the API's tokens into the screen-reader label ("8 plus box equals 11").
Equations are always drawn from tokens, never parsed from text.

## Next in Line

`src/games/sequences`: a row of five or six numbers that follows a pattern, with one or two blanks.
The child picks each missing number from four tiles. A round is five puzzles.

- **Start screen.** The same as Missing Number Chains: a big "Play" button, and under it "Or choose
  a level" with "Counting on", "Skip counting" and "Tricky patterns".
- **Play.** Before each puzzle the game asks `GET /players/me/next?game=sequences` and plays the
  level it is given. Sequences have no recommendation policy yet, so the answer is `no_policy`,
  level 1, every time; the game does not know or care, and will follow as soon as the backend
  recommends something else. With no answer the puzzle is level 1.
- **The row.** One block per number, in the block style of the other games. A blank is an empty
  dashed block; the one being solved is ringed in gold. With two blanks they are solved left to
  right: a solved blank fills in, turns green and stays.
- **Fitting the screen.** The row never wraps. Blocks share the width of the row, and the size of
  the numbers is worked out from that width, the number of terms and the longest number the row
  can hold (the visible terms and every option). Six blocks with four-digit numbers fit at 360 px;
  shorter numbers are drawn bigger. On a phone the row also takes most of the play area's padding.
- **Negative numbers** are written with the real minus sign, `−` (U+2212), never a hyphen, in the
  row and on the tiles, and are read as "minus 3" by a screen reader (`formatNumber` and
  `spokenNumber` in `sequence.ts`).
- **Answering, wrong answers, hints, problems.** As in Missing Number Chains, all through
  `usePuzzleSession`: keys 1 to 4 and Enter, the automatic hint after two wrong tries, tiers 1 to
  3, a silent restart on a 410, a friendly error with Try again. The diagnosis is logged with
  `console.debug` in development and never shown.
- **The visual hint.** Once the child has the second hint tier (the one that states the rule),
  small arcs are drawn between neighbouring numbers, each labelled with its jump: `+4`, or `−3`.
  On a growing sequence each arc shows its own gap. **Arcs are drawn only between two numbers the
  puzzle itself shows.** The differences are worked out in the browser from the visible terms
  (`visibleJumps`); the browser does not have the answers. There is never an arc into or out of a
  blank, not even one the child has already solved, so the arcs cannot give a missing number
  away. They are decoration for a hint the child has already read: hidden from screen readers,
  and with reduced motion they appear without animation.
- **Screen readers.** The row is a list whose label reads naturally: "4, 8, 12, blank, 20", and
  "4, 8, 12, 16, 20" once filled. The current blank is announced as "Blank 1 of 2". After a
  correct answer focus moves to the next blank, or to the solved screen.

`useSequencesGame.ts` is the thin layer on `usePuzzleSession`; `Sequences.tsx` only draws;
`sequence.ts` has the pure helpers. The test fixtures are in `src/test/sequenceBackend.ts`, typed
from the generated schema, one per level plus a growing-step row.

## Sum Grid

`src/games/sum-grid`: a small grid of numbers with a target at the end of every row and under
every column, and some cells blank. The child fills the blanks one at a time, from four tiles, in
the order the server gives: always a blank that is the only unknown left in its row or column. A
round is five puzzles.

- **Start screen.** The shared pattern: a big "Play" (the backend has no policy for this game yet
  and says so with `no_policy`, level 1; the game plays what it is told), then "Or choose a level"
  with "2 by 2", "3 by 3" and "Big numbers".
- **The grid.** Cells are blocks. Targets are "goal" blocks: pills with a double outline and no
  hard shadow, so the difference is a shape, not a colour. Blanks still to come are dashed and
  muted; the current one is ringed in gold; a solved one fills in green and locks.
- **Line highlight.** Nothing is highlighted at first: finding the line is part of the puzzle.
  When the first hint opens (asked for, or opened by itself after two wrong tries), the step's
  whole line lights up, cells and target, and stays lit for the rest of that step.
- **Fitting the screen.** A 3 by 3 grid plus targets is four blocks across. Blocks share the
  width, and the numbers are sized from it and from the longest number on show, so two-digit cells
  and three-digit targets fit at 360 px without scrolling sideways.
- **Everything else** (keys 1 to 4 and Enter, the automatic hint, hint tiers, the silent restart on
  a 410, the friendly error, no diagnosis on screen) is `usePuzzleSession`, as in the other games.
- **Screen readers.** The grid is a real `<table>`: rows and columns with a total at the end of
  each are what a table is, so cell-by-cell reading comes for free and no arrow-key behaviour is
  implied (an ARIA `grid` would promise one). Its accessible description reads the grid line by
  line: "Row 1: 3, blank, 9. Target 18. … Column targets: 8, 11." Targets read as "Target 18",
  waiting blanks as "blank", and the current blank as "Row 1, column 2. Blank 1 of 3.", which
  takes focus after each correct answer. The highlighted line is not announced on its own: the
  hint that lights it already says "Look at the top row".

`useSumGridGame.ts` is the thin layer on `usePuzzleSession`; `SumGrid.tsx` only draws; `grid.ts`
has the pure helpers. The test fixtures are in `src/test/sumGridBackend.ts`, typed from the
generated schema, one per level.

## Number Pyramid

`src/games/number-pyramid` is the first game. Every block in the pyramid is the sum of the two
blocks below it. The child taps an empty block, then a number tile from the tray to drop it in;
tapping a filled block sends its tile back. Empty blocks are offered bottom row first, so a child
can also just tap tiles in order.

A round has eight puzzles that get harder (`LEVELS` in `pyramid.ts`):

| Puzzles | Rows | Bottom-row numbers | Blocks given                                 |
| ------- | ---- | ------------------ | -------------------------------------------- |
| 1–2     | 3    | 1–5, then 1–9      | The bottom row (adding only)                 |
| 3–4     | 3    | 1–9, then 1–12     | Three scattered blocks (adding, subtracting) |
| 5–6     | 4    | 1–5, then 1–9      | The bottom row                               |
| 7–8     | 4    | 1–9, then 1–12     | Four scattered blocks                        |

- **Puzzles are generated**, not hand-written, from a seed (`generateRound(seed)`). The same seed
  always gives the same round; the app seeds from the clock. Puzzle 8 ends on the round-complete screen, and Play again starts a new round.
- **No guessing.** A puzzle is only used if every block can be worked out one sum at a time
  (`canDeduceAll`), which also means it has exactly one solution.
- **Tiles** are the missing numbers plus two or three near-miss extras.
- **Hints** (`getHint`) point at the next block that can be worked out and ask the sum ("What is
  4 + 1?") without giving the answer. If that block already holds a wrong number, ORBI asks for
  another look at it.

`pyramid.ts` holds all the puzzle logic as pure functions; `NumberPyramid.tsx` is the play area and
state. Feedback, hints UI, sounds and the completion screen all come from `GameShell`.

## The demo page

Open `http://localhost:5173/#shell-demo`. `src/dev/ShellDemo.tsx` renders one dummy puzzle ("Tap the number that makes 10 with 7") inside the
shell. The dashed dev toolbar above it switches the `house` prop and forces each feedback state, so
every visual state can be reviewed in all five house colors. Choose **live** to hand control back to
the puzzle.

## Design system

### Tokens

`src/design/tokens.css` defines every token as a CSS custom property. `src/design/tokens.ts` mirrors
them with types, including the `HouseKey` union. `tokens.test.ts` fails if the two files drift
apart, so change both together.

Colors, spacing and type sizes come from the Martians Space Club design bundle. Two things are
defined here instead: motion timing (durations and easing curves), which the design leaves open, and
the look described under [Visual style](#visual-style).

| Group      | Tokens                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Color      | `--color-space`, `-space-2`, `-space-3` (backdrop) · `--color-gold`, `-gold-deep` · `--color-ink`, `-ink-2`, `-on-dark`, `-on-dark-muted` (text) · `--color-outline` (block outlines and hard shadows) · `--color-paper`, `-cream`, `-sand`, `-line` (surfaces) · `--color-magenta`, `-peach`, `-lavender`, `-mint` (accents) · `--color-correct-bg/-text`, `--color-retry-bg/-text` (feedback) |
| House      | `--house-<key>`, `--house-<key>-dark`, `--house-<key>-soft`, `--house-<key>-strong` for `navigators`, `builders`, `cultivators`, `artisans`, `scientists` · active house: `--house`, `--house-dark`, `--house-soft`, `--house-strong`                                                                                                                                                           |
| Typography | Families `--font-pop` and `--font-display` (Outfit), `--font-body` and `--font-reading` (Lexend) · weights `--font-weight-regular/medium/bold/heavy` (400/500/700/800) · sizes `--font-size-xs/sm/md/lg/xl/2xl/3xl/display` (12/13/15/17/21/26/34/40 px) · `--line-height-tight/snug/body` · `--letter-spacing-label`                                                                           |
| Spacing    | 4 px base: `--space-1/2/3/4/5/6/8/10/12/16` (4/8/12/16/20/24/32/40/48/64 px) · `--size-touch-min` (44 px), `--size-control` (52 px), `--size-outline` (3 px), `--size-press` (4 px)                                                                                                                                                                                                             |
| Radius     | `--radius-sm/md/lg/xl` (6/8/12/16 px), `--radius-pill`                                                                                                                                                                                                                                                                                                                                          |
| Shadow     | `--shadow-tile`, `--shadow-soft`, `--shadow-card`, `--shadow-panel`, `--shadow-button`: all hard-edged, no blur                                                                                                                                                                                                                                                                                 |
| Focus      | `--focus-ring-width`, `--focus-ring-color` (gold), `--focus-ring-edge` (dark edge so the ring shows on light surfaces)                                                                                                                                                                                                                                                                          |
| Motion     | `--duration-fast/base/slow/celebrate` (120/220/420/900 ms), `--duration-float`, `--duration-twinkle` (ambient loops) · `--ease-standard/out/bounce/ambient`                                                                                                                                                                                                                                     |

### Visual style

The palette and the space backdrop are the Martians Space Club ones. On top of them sits a
retro-platformer layer:

- **Type:** modern sans-serif only. Outfit (700/800) for headings, buttons and numbers; Lexend for
  body text. No rounded or hand-drawn faces.
- **Blocks:** panels, tiles and buttons have a 3 px dark outline (`--color-outline`,
  `--size-outline`), small radii and a hard shadow with no blur.
- **Press:** buttons sit on a 5 px shadow (`--shadow-button`) and sink by `--size-press` when
  pressed. A selected option stays pressed in.
- **Details:** square progress blocks that turn gold, square stars on the backdrop, and a hard
  drop shadow on the big headings.

Build new game controls the same way: outline, hard shadow, press-down.

**Switching house.** Set `data-house="<key>"` on any element and the four active-house variables
update for everything inside it. `GameShell` does this from its `house` prop.

**Easy-reading mode.** Set `data-reading-font="lexend"` on an ancestor to swap the heading family to
Lexend as well (body text already uses it). Nothing in the UI toggles it yet.

**Reduced motion.** Under `prefers-reduced-motion: reduce` every `--duration-*` token drops to
`0.01ms` and looping animations run once. Build animations from the duration tokens and they
respect the setting automatically.

### Color contrast

White text on the base house color fails WCAG AA at normal text size for four of the five houses.
Each house therefore has a `-strong` shade that is safe for text:

| House       | Base      | White on base | Strong    | White on strong |
| ----------- | --------- | ------------- | --------- | --------------- |
| navigators  | `#7C4DEF` | 5.04          | `#5226B5` | 9.12            |
| builders    | `#E86E48` | 3.11          | `#A8481F` | 5.81            |
| cultivators | `#15A589` | 3.10          | `#0B6B58` | 6.45            |
| artisans    | `#E94E8E` | 3.53          | `#B22C66` | 6.10            |
| scientists  | `#1F9BB5` | 3.27          | `#0F6276` | 6.93            |

Rules of use:

- `--house`: decoration only (borders, glows, swatches, fills with no text on them).
- `--house-strong`: text on light surfaces, and fills that carry white text.
- `--house-soft`: pale background for `--house-strong` text.
- Gold carries ink text, never white. Gold text belongs on the space backdrop only.

`src/design/contrast.test.ts` computes the ratios and fails if any text pairing drops below 4.5:1.
It covers body text on the backdrop, text on light surfaces, text on gold, the feedback messages,
and each house's strong, dark and soft pairings.

## GameShell contract

`GameShell` (`src/shell`) is the one layout every game uses.

```tsx
import { GameShell, type FeedbackState } from './shell';

<GameShell
  title="Make Ten"
  instruction="Tap the number that makes 10 with 7"
  house="navigators"
  progress={{ current: 3, total: 8 }}
  feedback={feedback}
  hint={hint}
  onHint={showHint}
  onCheck={check}
  onReset={reset}
  onNext={next}
>
  {/* the play area */}
</GameShell>;
```

| Prop                           | Type                                                           | Notes                                                                                           |
| ------------------------------ | -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `title`                        | `string`                                                       | Small, top left                                                                                 |
| `instruction`                  | `string`                                                       | The one instruction on screen; rendered as the `<h1>`                                           |
| `house`                        | `HouseKey`                                                     | Accent color for the whole shell                                                                |
| `progress`                     | `{ current: number; total: number }`                           | `current` is 1-based                                                                            |
| `feedback`                     | `'idle' \| 'correct' \| 'incorrect' \| 'solved' \| 'complete'` | Drives all shared feedback                                                                      |
| `hint`                         | `string \| null` (optional)                                    | Shown in ORBI's bubble when present                                                             |
| `onHint`, `onCheck`, `onReset` | `() => void` (optional)                                        | A button without a handler is disabled, never removed                                           |
| `onExit`                       | `() => void` (optional)                                        | Shows a "Games" button in the header that calls it; omitted means no button                     |
| `onNext`                       | `() => void` (optional)                                        | "Next" on the solved screen, "Play again" on the round-complete screen; omitted means no button |
| `children`                     | `ReactNode`                                                    | The play area                                                                                   |

### What a game provides

- The play area, as `children`, and all puzzle logic and state.
- The current `feedback` state. For the last puzzle of a round, set `'complete'` instead of
  `'solved'`; `onNext` then means "play again". Set it back to `'idle'` when the child changes their answer, so the
  next result animates and is announced again.
- The `hint` text when the child asks for one (`onHint`), and `null` to clear it.
- Its own controls inside the play area: touch targets of at least 44×44 px (`--size-touch-min`),
  reachable by keyboard, styled with tokens. The global gold focus ring applies automatically.

### What the shell handles

- **Layout:** title and progress at the top, one instruction heading, the play area, and the action
  bar with Hint, Check and Reset always in the same order and place.
- **Progress:** segments up to 12 puzzles, a single bar beyond that, plus the "3 / 8" count and an
  accessible `progressbar`.
- **Feedback:** a pulse and a green outline on the play area for `correct`; a gentle shake, an encouraging
  message and a nudge on the Hint button for `incorrect` (no red, no error wording); a full
  completion screen with a celebration and the Next button for `solved`; a round-complete screen for `complete`, with a bigger celebration, one gold block per puzzle and a Play again button. The play area stays mounted
  behind the completion screen, so a game keeps its state.
- **Sound:** short synthesized tones for each feedback state (`useFeedbackSound`, Web Audio API, no
  audio files) and the mute toggle in the header. Sound starts muted and turns on at the first tap
  or key press, unless the user has set the toggle themselves.
- **Hints:** ORBI's speech bubble. ORBI is placeholder art in
  `src/shell/orbi/OrbiPlaceholder.tsx`; replace the SVG there and nothing else changes.
- **Accessibility:** feedback announced through an always-mounted `aria-live="polite"` region,
  hints announced through a second one, keyboard focus moved to Next or Play again on the completion screens, icons
  paired with text labels, and reduced-motion support through the motion tokens.

Games should never draw their own feedback banners, completion screens, hint UI or sounds.
