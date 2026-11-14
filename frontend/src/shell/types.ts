import type { ReactNode } from 'react';
import type { HouseKey } from '../design/tokens';

/**
 * - idle:      nothing to report; the child is working on the puzzle.
 * - correct:   the last check was right (play area pulses).
 * - incorrect: the last check was wrong (gentle shake, nudge toward the hint).
 * - solved:    the puzzle is finished (completion screen replaces the play area).
 * - complete:  the last puzzle of the round is finished (round-complete screen,
 *              with a bigger celebration and "Play again"). Use it instead of
 *              'solved' for the final puzzle.
 *
 * Set the state back to 'idle' when the child changes their answer, so the
 * next 'correct' or 'incorrect' animates and is announced again.
 */
export type FeedbackState = 'idle' | 'correct' | 'incorrect' | 'solved' | 'complete';

/** What the completion screen says instead of its usual words, for a puzzle played outside a round. */
export interface SolvedCopy {
  /** The line under the heading, for example "Come back tomorrow for a new puzzle!". */
  message: string;
  /** The button's label, for example "More games". */
  nextLabel: string;
}

export interface GameProgress {
  /** 1-based position of the current puzzle. */
  current: number;
  total: number;
}

export interface GameShellProps {
  /** Short game name, shown small at the top left. */
  title: string;
  /** The one instruction visible right now. Rendered as the page heading. */
  instruction: string;
  /** Sets the accent color for the whole shell. */
  house: HouseKey;
  progress: GameProgress;
  feedback: FeedbackState;
  /** Shown in ORBI's hint bubble when present. */
  hint?: string | null;
  /** Each action button is disabled while its handler is missing. */
  onHint?: () => void;
  onCheck?: () => void;
  onReset?: () => void;
  /** Used by "Next" on the solved screen and by "Play again" on the round-complete screen. */
  onNext?: () => void;
  /**
   * Other words for the solved screen ('solved' feedback), when the puzzle is
   * not one of a round: Today's Puzzle says "Come back tomorrow" there.
   */
  solvedScreen?: SolvedCopy;
  /**
   * Leaves the game. When given, the header shows a "Games" button that calls
   * it; without it there is no such button.
   */
  onExit?: () => void;
  /** The play area. */
  children: ReactNode;
}
