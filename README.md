# Mathlings

Short math-logic puzzle games for kids aged 7–12. This is a standalone precursor to the
Martians Space Club site and will be merged into it later, so its visual language comes from that
site's design.

Right now the project contains the frontend scaffold, the design system and the `GameShell` that
every game renders inside. There are no real games, routing, backend or persistence yet.

## Getting started

```bash
npm install
npm run dev        # demo page at http://localhost:5173
```

| Script                 | What it does                                |
| ---------------------- | ------------------------------------------- |
| `npm run dev`          | Vite dev server with the shell demo page    |
| `npm test`             | Vitest, single run                          |
| `npm run test:watch`   | Vitest in watch mode                        |
| `npm run lint`         | ESLint                                      |
| `npm run typecheck`    | TypeScript (strict), no emit                |
| `npm run format`       | Prettier, write                             |
| `npm run format:check` | Prettier, check only                        |
| `npm run build`        | Typecheck, then production build to `dist/` |

Stack: Vite, React, TypeScript (strict), plain CSS with custom properties and CSS Modules, Vitest
with React Testing Library, `lucide-react` icons, and fonts self-hosted through `@fontsource/*`.

```
src/
  design/   tokens.css, tokens.ts, global.css, contrast helpers and their tests
  shell/    GameShell and its parts (progress, action bar, hint bubble, solved screen, sound hook)
  dev/      ShellDemo: the review page mounted at the app root for now
```

## The demo page

`src/dev/ShellDemo.tsx` renders one dummy puzzle ("Tap the number that makes 10 with 7") inside the
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

| Prop                           | Type                                             | Notes                                                 |
| ------------------------------ | ------------------------------------------------ | ----------------------------------------------------- |
| `title`                        | `string`                                         | Small, top left                                       |
| `instruction`                  | `string`                                         | The one instruction on screen; rendered as the `<h1>` |
| `house`                        | `HouseKey`                                       | Accent color for the whole shell                      |
| `progress`                     | `{ current: number; total: number }`             | `current` is 1-based                                  |
| `feedback`                     | `'idle' \| 'correct' \| 'incorrect' \| 'solved'` | Drives all shared feedback                            |
| `hint`                         | `string \| null` (optional)                      | Shown in ORBI's bubble when present                   |
| `onHint`, `onCheck`, `onReset` | `() => void` (optional)                          | A button without a handler is disabled, never removed |
| `onNext`                       | `() => void` (optional)                          | "Next" on the solved screen; omitted means no button  |
| `children`                     | `ReactNode`                                      | The play area                                         |

### What a game provides

- The play area, as `children`, and all puzzle logic and state.
- The current `feedback` state. Set it back to `'idle'` when the child changes their answer, so the
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
  completion screen with a celebration and the Next button for `solved`. The play area stays mounted
  behind the completion screen, so a game keeps its state.
- **Sound:** short synthesized tones for each feedback state (`useFeedbackSound`, Web Audio API, no
  audio files) and the mute toggle in the header. Sound starts muted and turns on at the first tap
  or key press, unless the user has set the toggle themselves.
- **Hints:** ORBI's speech bubble. ORBI is placeholder art in
  `src/shell/orbi/OrbiPlaceholder.tsx`; replace the SVG there and nothing else changes.
- **Accessibility:** feedback announced through an always-mounted `aria-live="polite"` region,
  hints announced through a second one, keyboard focus moved to Next on the solved screen, icons
  paired with text labels, and reduced-motion support through the motion tokens.

Games should never draw their own feedback banners, completion screens, hint UI or sounds.
