import type { ReactNode } from 'react';
import type { HouseKey } from '../design/tokens';

/**
 * - idle:      nothing to report; the child is working on the puzzle.
 * - correct:   the last check was right (play area pulses).
 * - incorrect: the last check was wrong (gentle shake, nudge toward the hint).
 * - solved:    the puzzle is finished (completion screen replaces the play area).
 *
 * Set the state back to 'idle' when the child changes their answer, so the
 * next 'correct' or 'incorrect' animates and is announced again.
 */
export type FeedbackState = 'idle' | 'correct' | 'incorrect' | 'solved';

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
  /** Used by the "Next" button on the solved screen. */
  onNext?: () => void;
  /** The play area. */
  children: ReactNode;
}
