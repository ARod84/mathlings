import { useCallback, useEffect, useReducer, useRef } from 'react';
import {
  checkStep,
  getHint,
  newMissingNumber,
  type ApiResult,
  type Diagnosis,
  type Level,
  type PuzzlePublic,
} from '../../api/puzzles';
import type { FeedbackState } from '../../shell';

/*
 * All the logic and state of Missing Number Chains. The component only draws
 * what this hook returns and calls its actions.
 *
 * A round is five puzzles at one level. Each puzzle is a chain of steps that
 * the child solves one at a time; the server checks every answer.
 */

/** Chain length of each puzzle in a round. */
export const ROUND_LENGTHS = [2, 2, 3, 3, 4] as const;
/** After this many wrong tries on a step, a hint opens by itself. */
export const WRONG_TRIES_BEFORE_HINT = 2;

export interface GameTiming {
  /** How long "correct" shows before the next step slides in. */
  advanceMs: number;
  /** How long "correct" shows before the completion screen. */
  finishMs: number;
}

export const DEFAULT_TIMING: GameTiming = { advanceMs: 900, finishMs: 1100 };

export type Phase = 'choose-level' | 'loading' | 'playing' | 'error';

/** What to do again when the child presses "Try again". */
type Retry =
  | { kind: 'load'; level: Level; puzzleIndex: number }
  | { kind: 'check' }
  | { kind: 'hint'; tier: number };

export interface GameState {
  phase: Phase;
  level: Level | null;
  /** 0-based position of the current puzzle in the round. */
  puzzleIndex: number;
  puzzle: PuzzlePublic | null;
  /** 0-based position of the current step in the chain. */
  stepIndex: number;
  /** The option in the box of the current step, if any. */
  selected: number | null;
  /** The answers of the steps solved so far, in order. */
  answers: number[];
  feedback: FeedbackState;
  /** A check is on its way to the server. */
  checking: boolean;
  /** Wrong tries on the current step. */
  wrongTries: number;
  /** Highest hint tier shown for the current step; 0 for none. */
  hintTier: number;
  hint: string | null;
  hintLoading: boolean;
  /** The server's view of the last answer. Kept for later; never shown to the child. */
  lastDiagnosis: Diagnosis | null;
}

const INITIAL: GameState = {
  phase: 'choose-level',
  level: null,
  puzzleIndex: 0,
  puzzle: null,
  stepIndex: 0,
  selected: null,
  answers: [],
  feedback: 'idle',
  checking: false,
  wrongTries: 0,
  hintTier: 0,
  hint: null,
  hintLoading: false,
  lastDiagnosis: null,
};

const FRESH_STEP = {
  selected: null,
  feedback: 'idle',
  checking: false,
  wrongTries: 0,
  hintTier: 0,
  hint: null,
  hintLoading: false,
} satisfies Partial<GameState>;

type Action =
  | { type: 'loading'; level: Level; puzzleIndex: number }
  | { type: 'loaded'; puzzle: PuzzlePublic }
  | { type: 'failed' }
  | { type: 'resumed' }
  | { type: 'selected'; value: number }
  | { type: 'cleared' }
  | { type: 'checking' }
  | { type: 'correct'; answer: number; diagnosis: Diagnosis }
  | { type: 'incorrect'; diagnosis: Diagnosis }
  | { type: 'advanced'; stepIndex: number }
  | { type: 'finished'; feedback: 'solved' | 'complete' }
  | { type: 'hintLoading' }
  | { type: 'hint'; tier: number; text: string }
  | { type: 'hintFailed' }
  | { type: 'restarted' };

function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case 'loading':
      return {
        ...INITIAL,
        phase: 'loading',
        level: action.level,
        puzzleIndex: action.puzzleIndex,
      };
    case 'loaded':
      return {
        ...state,
        ...FRESH_STEP,
        phase: 'playing',
        puzzle: action.puzzle,
        stepIndex: 0,
        answers: [],
      };
    case 'failed':
      return { ...state, phase: 'error', checking: false, hintLoading: false };
    case 'resumed':
      return { ...state, phase: 'playing' };
    case 'selected':
      // Changing the answer clears the last result, so the next one is announced again.
      return { ...state, selected: action.value, feedback: 'idle' };
    case 'cleared':
      return { ...state, selected: null, feedback: 'idle' };
    case 'checking':
      return { ...state, checking: true };
    case 'correct':
      return {
        ...state,
        checking: false,
        feedback: 'correct',
        answers: [...state.answers, action.answer],
        lastDiagnosis: action.diagnosis,
      };
    case 'incorrect':
      // The box stays filled, so the child can see what they tried.
      return {
        ...state,
        checking: false,
        feedback: 'incorrect',
        wrongTries: state.wrongTries + 1,
        lastDiagnosis: action.diagnosis,
      };
    case 'advanced':
      return { ...state, ...FRESH_STEP, stepIndex: action.stepIndex };
    case 'finished':
      return { ...state, feedback: action.feedback };
    case 'hintLoading':
      return { ...state, hintLoading: true };
    case 'hint':
      return { ...state, hintLoading: false, hintTier: action.tier, hint: action.text };
    case 'hintFailed':
      return { ...state, hintLoading: false };
    case 'restarted':
      return INITIAL;
  }
}

export interface MissingNumberGame {
  state: GameState;
  /** Number of puzzles in a round. */
  roundSize: number;
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
  const [state, dispatch] = useReducer(reducer, INITIAL);

  // The callbacks below run after awaits, so they read the latest state from a ref.
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  // One controller for the game's lifetime: leaving the game cancels whatever is in flight.
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const failed = useRef<Retry | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    abort.current = controller;
    return () => {
      controller.abort();
      window.clearTimeout(timer.current);
    };
  }, []);

  /** False once the child has left: the result must be dropped. */
  const alive = () => abort.current !== null && !abort.current.signal.aborted;

  const fail = useCallback((retry: Retry) => {
    failed.current = retry;
    dispatch({ type: 'failed' });
  }, []);

  const loadPuzzle = useCallback(
    async (level: Level, puzzleIndex: number) => {
      dispatch({ type: 'loading', level, puzzleIndex });
      const length = ROUND_LENGTHS[puzzleIndex] ?? ROUND_LENGTHS[0];
      const result = await newMissingNumber({ level, length }, abort.current?.signal);
      if (!alive()) return;
      if (result.status === 'ok') dispatch({ type: 'loaded', puzzle: result.data });
      else fail({ kind: 'load', level, puzzleIndex });
    },
    [fail],
  );

  /**
   * What every call about an existing puzzle does when it does not succeed.
   * A puzzle from an older generator version is replaced by a fresh one at
   * the same level, without a word; anything else shows the friendly error.
   */
  const handleFailure = useCallback(
    (result: ApiResult<unknown>, retry: Retry) => {
      const { level, puzzleIndex } = latest.current;
      if (result.status === 'gone' && level !== null) void loadPuzzle(level, puzzleIndex);
      else fail(retry);
    },
    [fail, loadPuzzle],
  );

  const fetchHint = useCallback(
    async (tier: number) => {
      const { puzzle, stepIndex } = latest.current;
      if (!puzzle) return;
      dispatch({ type: 'hintLoading' });
      const result = await getHint(puzzle.puzzle_id, stepIndex, tier, abort.current?.signal);
      if (!alive()) return;
      // The child may have moved on while the hint was on its way.
      const now = latest.current;
      if (now.puzzle?.puzzle_id !== puzzle.puzzle_id || now.stepIndex !== stepIndex) return;
      if (result.status === 'ok') {
        dispatch({ type: 'hint', tier: result.data.tier, text: result.data.text });
      } else {
        dispatch({ type: 'hintFailed' });
        handleFailure(result, { kind: 'hint', tier });
      }
    },
    [handleFailure],
  );

  const check = useCallback(async () => {
    const { puzzle, stepIndex, selected, checking, feedback, puzzleIndex, wrongTries, hintTier } =
      latest.current;
    if (!puzzle || selected === null || checking || feedback === 'correct') return;
    dispatch({ type: 'checking' });
    const result = await checkStep(puzzle.puzzle_id, stepIndex, selected, abort.current?.signal);
    if (!alive()) return;
    if (result.status !== 'ok') {
      handleFailure(result, { kind: 'check' });
      return;
    }

    const { correct, diagnosis, next_step: nextStep } = result.data;
    // For later (adaptive practice). Never shown to the child.
    if (import.meta.env.DEV) console.debug('[missing-number] diagnosis', diagnosis);

    if (!correct) {
      dispatch({ type: 'incorrect', diagnosis });
      // On the second wrong try a hint opens by itself, but never the last
      // tier: that one shows the answer, and the child has to ask for it.
      const totalTiers = puzzle.steps[stepIndex]?.hint_tiers ?? 0;
      const nextTier = hintTier + 1;
      if (wrongTries + 1 === WRONG_TRIES_BEFORE_HINT && nextTier < totalTiers) {
        void fetchHint(nextTier);
      }
      return;
    }

    dispatch({ type: 'correct', answer: selected, diagnosis });
    window.clearTimeout(timer.current);
    if (nextStep !== null) {
      timer.current = window.setTimeout(
        () => dispatch({ type: 'advanced', stepIndex: nextStep }),
        timing.advanceMs,
      );
    } else {
      const lastPuzzle = puzzleIndex === ROUND_LENGTHS.length - 1;
      timer.current = window.setTimeout(
        () => dispatch({ type: 'finished', feedback: lastPuzzle ? 'complete' : 'solved' }),
        timing.finishMs,
      );
    }
  }, [fetchHint, handleFailure, timing.advanceMs, timing.finishMs]);

  const locked = state.checking || state.feedback === 'correct' || state.phase !== 'playing';
  const totalTiers = state.puzzle?.steps[state.stepIndex]?.hint_tiers ?? 0;
  const canHint = !locked && !state.hintLoading && state.hintTier < totalTiers;

  const select = useCallback((value: number) => {
    const { checking, feedback, phase } = latest.current;
    if (phase === 'playing' && !checking && feedback !== 'correct') {
      dispatch({ type: 'selected', value });
    }
  }, []);

  const requestHint = useCallback(() => {
    const { puzzle, stepIndex, hintTier, hintLoading } = latest.current;
    const tiers = puzzle?.steps[stepIndex]?.hint_tiers ?? 0;
    if (!hintLoading && hintTier < tiers) void fetchHint(hintTier + 1);
  }, [fetchHint]);

  const next = useCallback(() => {
    const { level, puzzleIndex, feedback } = latest.current;
    if (level === null || feedback === 'complete') dispatch({ type: 'restarted' });
    else void loadPuzzle(level, puzzleIndex + 1);
  }, [loadPuzzle]);

  const retry = useCallback(() => {
    const again = failed.current;
    if (again === null) return;
    failed.current = null;
    if (again.kind === 'load') {
      void loadPuzzle(again.level, again.puzzleIndex);
      return;
    }
    // The puzzle is still there: go back to it, then repeat the call.
    dispatch({ type: 'resumed' });
    if (again.kind === 'check') void check();
    else void fetchHint(again.tier);
  }, [check, fetchHint, loadPuzzle]);

  return {
    state,
    roundSize: ROUND_LENGTHS.length,
    chooseLevel: useCallback((level: Level) => void loadPuzzle(level, 0), [loadPuzzle]),
    select,
    check: useCallback(() => void check(), [check]),
    requestHint,
    reset: useCallback(() => dispatch({ type: 'cleared' }), []),
    next,
    retry,
    locked,
    canHint,
  };
}
