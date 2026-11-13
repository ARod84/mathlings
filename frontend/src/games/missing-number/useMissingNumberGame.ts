import { useCallback } from 'react';
import { isLevel, type Level, type MistakeRule, type PuzzlePublic } from '../../api/puzzles';
import {
  DEFAULT_TIMING,
  usePuzzleSession,
  WRONG_TRIES_BEFORE_HINT,
  type Phase,
  type PuzzleSessionConfig,
  type SessionState,
  type SessionTiming,
} from '../usePuzzleSession';

/*
 * Missing Number Chains on top of the shared puzzle session. Everything about
 * loading, checking, hints, errors and leaving is in ../usePuzzleSession.ts.
 * This file says what is particular to chains: how a round picks its puzzles.
 *
 * A round is five puzzles. Each puzzle is a chain of steps that the child
 * solves one at a time; the server checks every answer.
 *
 * There are two ways to play a round:
 * - "Play" (adaptive): before every puzzle the backend is asked what this
 *   player should do next, and its level and chain length are used, along
 *   with its focus (a mistake to target), which is passed straight on to
 *   the puzzle request and never shown or mentioned to the child. If it
 *   cannot say (no player id, or the call fails) the puzzle is FALLBACK, and
 *   the child is told nothing.
 * - A chosen range (fixed): all five puzzles at that level, with the chain
 *   lengths in ROUND_LENGTHS.
 */

/** Chain length of each puzzle in a round at a chosen level. */
export const ROUND_LENGTHS = [2, 2, 3, 3, 4] as const;
/** What "Play" uses when the backend has no recommendation. */
export const FALLBACK = { level: 1, length: 2 } as const;

export { DEFAULT_TIMING, WRONG_TRIES_BEFORE_HINT };
export type { Phase };
export type GameTiming = SessionTiming;

/** How the puzzles of a round are picked. */
type Plan = { kind: 'adaptive' } | { kind: 'fixed'; level: Level };

export type GameState = SessionState<PuzzlePublic, Plan, Level>;

const SESSION: PuzzleSessionConfig<'missing-number', Plan, Level> = {
  game: 'missing-number',
  roundSize: ROUND_LENGTHS.length,
  asksBackend: (plan) => plan.kind === 'adaptive',
  fixedLevel: (plan) => (plan.kind === 'fixed' ? plan.level : null),
  choose: (plan, puzzleIndex, recommended) => {
    let level: Level;
    let length: number;
    // A mistake rule for the backend to target, from /next. Opaque to the game.
    let focus: MistakeRule | null = null;
    if (plan.kind === 'fixed') {
      level = plan.level;
      length = ROUND_LENGTHS[puzzleIndex] ?? ROUND_LENGTHS[0];
    } else if (
      recommended !== null &&
      isLevel(recommended.level) &&
      recommended.length !== null &&
      recommended.length > 0
    ) {
      level = recommended.level;
      length = recommended.length;
      focus = recommended.focus;
    } else {
      // No recommendation: a short, easy puzzle, and not a word about it.
      level = FALLBACK.level;
      length = FALLBACK.length;
    }
    // The focus is sent only when there is one.
    return { level, request: focus === null ? { level, length } : { level, length, focus } };
  },
  hintTiers: (puzzle, stepIndex) => puzzle.steps[stepIndex]?.hint_tiers ?? 0,
};

export interface MissingNumberGame {
  state: GameState;
  /** Number of puzzles in a round. */
  roundSize: number;
  /** Starts a round that follows the backend's recommendation, puzzle by puzzle. */
  play: () => void;
  /** Starts a round at one level. */
  chooseLevel: (level: Level) => void;
  select: (value: number) => void;
  /** Sends the boxed number to the server. Does nothing without one. */
  check: () => void;
  /** Fetches the next hint tier for the current step. */
  requestHint: () => void;
  /** Empties the box of the current step. */
  reset: () => void;
  /** After a solved puzzle: the next one. After the round: back to the start screen. */
  next: () => void;
  /** On the error screen: do the thing that failed again. */
  retry: () => void;
  /** No answer can be changed right now (a check is running or the step is done). */
  locked: boolean;
  canHint: boolean;
}

export function useMissingNumberGame(timing: GameTiming = DEFAULT_TIMING): MissingNumberGame {
  const { start, ...session } = usePuzzleSession(SESSION, timing);
  return {
    ...session,
    play: useCallback(() => start({ kind: 'adaptive' }), [start]),
    chooseLevel: useCallback((level: Level) => start({ kind: 'fixed', level }), [start]),
  };
}
