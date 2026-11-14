import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from 'react';
import { getNextPuzzle, type NextPuzzle } from '../api/player';
import {
  checkStep,
  getHint,
  newPuzzle,
  type ApiResult,
  type CheckContext,
  type Diagnosis,
  type GameId,
  type NewPuzzleRequest,
  type PuzzleOf,
} from '../api/puzzles';
import type { FeedbackState, SolvedCopy } from '../shell';

/*
 * A round of server-checked puzzles, for any game the backend has a puzzle
 * type for. It owns everything that is the same from game to game:
 *
 * - loading a puzzle, and asking the backend what to play next before it
 * - checking an answer, step by step, with the server deciding what is right
 * - hint tiers, and the hint that opens by itself after two wrong tries
 * - a puzzle from an older generator version (410): replaced without a word
 * - the friendly error state and "Try again"
 * - dropping every result that arrives after the child has left
 *
 * A game supplies a PuzzleSessionConfig: its id, where the level and the
 * request parameters come from, and how many hint tiers a step has. Its own
 * hook (see missing-number/useMissingNumberGame.ts) is then a thin layer that
 * names the ways to start a round.
 *
 * There is a second way to play, besides a round: one puzzle that was fetched
 * already (SinglePuzzle). Today's Puzzle uses it. The game starts on that
 * puzzle with no start screen, every check carries the puzzle's context, and
 * when it is solved the completion screen says what the caller asked for.
 *
 * An answer is a number, because that is what the check route takes.
 */

/** After this many wrong tries on a step, a hint opens by itself. */
export const WRONG_TRIES_BEFORE_HINT = 2;

export interface SessionTiming {
  /** How long "correct" shows before the next step slides in. */
  advanceMs: number;
  /** How long "correct" shows before the completion screen. */
  finishMs: number;
}

export const DEFAULT_TIMING: SessionTiming = { advanceMs: 900, finishMs: 1100 };

export type Phase = 'choose-level' | 'loading' | 'playing' | 'error';

/** The puzzle to ask the backend for. */
export interface PuzzleChoice<G extends GameId, Level> {
  /** Kept in the state, for the game to show. */
  level: Level;
  /** The game's own new-puzzle body, sent exactly as it is. */
  request: NewPuzzleRequest<G>;
}

/**
 * What a game tells the session. `Plan` is the game's own description of how
 * a round picks its puzzles (for example "adaptive", or "fixed at level 2").
 *
 * Define the config once, outside the component: the session's callbacks
 * depend on it.
 */
export interface PuzzleSessionConfig<G extends GameId, Plan, Level> {
  /** The game's name in the API. */
  game: G;
  /** Number of puzzles in a round. */
  roundSize: number;

  // ---- where the level and the parameters come from ----

  /** True if the backend is asked what to play before every puzzle of this plan. */
  asksBackend: (plan: Plan) => boolean;
  /** The level the plan fixes, or null when only the backend's answer decides it. */
  fixedLevel: (plan: Plan) => Level | null;
  /**
   * The puzzle to ask for. `recommended` is the backend's answer when the
   * plan asks for one, and null when it does not or there was no answer; the
   * game then falls back to something sensible, and the child is told nothing.
   */
  choose: (
    plan: Plan,
    puzzleIndex: number,
    recommended: NextPuzzle | null,
  ) => PuzzleChoice<G, Level>;

  // ---- what only the game knows about its puzzles ----

  /** How many hint tiers a step has; 0 for a step that is not there. */
  hintTiers: (puzzle: PuzzleOf<G>, stepIndex: number) => number;
}

/**
 * "Play this one puzzle": a puzzle already in hand, played outside a round.
 * The session starts on it (no start screen), sends `context` with every
 * check, and shows `solved` when it is done. Define it per render if you
 * like: the session reads the latest one.
 */
export interface SinglePuzzle<G extends GameId, Level> {
  puzzle: PuzzleOf<G>;
  level: Level;
  /** Sent with every check, so the backend can tell this play apart. */
  context: CheckContext;
  /**
   * The same puzzle again, for the one case where the server says the puzzle
   * in hand is from an older generator version (410). Tried once; if that
   * also fails, the child sees the usual "Try again".
   */
  reload: (signal?: AbortSignal) => Promise<ApiResult<PuzzleOf<G>>>;
  /** Called once, as soon as the last step is answered correctly. */
  onSolved?: () => void;
  /** What the completion screen says, and what its button does. */
  solved: SolvedCopy & { onNext: () => void };
}

/** What to do again when the child presses "Try again". */
type Retry<Plan> =
  | { kind: 'load'; plan: Plan; puzzleIndex: number }
  | { kind: 'reload' }
  | { kind: 'check' }
  | { kind: 'hint'; tier: number };

export interface SessionState<Puzzle, Plan, Level> {
  phase: Phase;
  /** How this round picks its puzzles. Null before a round starts. */
  plan: Plan | null;
  /** The level of the current puzzle; null until the first one has loaded, if the plan fixes none. */
  level: Level | null;
  /** 0-based position of the current puzzle in the round. */
  puzzleIndex: number;
  puzzle: Puzzle | null;
  /** 0-based position of the current step in the puzzle. */
  stepIndex: number;
  /** The answer picked for the current step, if any. */
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

// Every game-specific field starts as null, so this fits any game's state.
const INITIAL: SessionState<never, never, never> = {
  phase: 'choose-level',
  plan: null,
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
} satisfies Partial<SessionState<never, never, never>>;

/** Where a session begins: the start screen, or straight into a single puzzle. */
function initialState<Puzzle, Plan, Level>(
  single: { puzzle: Puzzle; level: Level } | undefined,
): SessionState<Puzzle, Plan, Level> {
  const initial = INITIAL as SessionState<Puzzle, Plan, Level>;
  if (!single) return initial;
  return { ...initial, phase: 'playing', puzzle: single.puzzle, level: single.level };
}

type Action<Puzzle, Plan, Level> =
  | { type: 'loading'; plan: Plan; level: Level | null; puzzleIndex: number }
  | { type: 'reloading' }
  | { type: 'loaded'; puzzle: Puzzle; level: Level }
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

function reducer<Puzzle, Plan, Level>(
  state: SessionState<Puzzle, Plan, Level>,
  action: Action<Puzzle, Plan, Level>,
): SessionState<Puzzle, Plan, Level> {
  switch (action.type) {
    case 'loading':
      return {
        ...INITIAL,
        phase: 'loading',
        plan: action.plan,
        level: action.level,
        puzzleIndex: action.puzzleIndex,
      };
    case 'reloading':
      // The same puzzle is on its way again; the level is already known.
      return { ...INITIAL, phase: 'loading', level: state.level };
    case 'loaded':
      return {
        ...state,
        ...FRESH_STEP,
        phase: 'playing',
        puzzle: action.puzzle,
        level: action.level,
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
      // The answer stays in place, so the child can see what they tried.
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

export interface PuzzleSession<G extends GameId, Plan, Level> {
  state: SessionState<PuzzleOf<G>, Plan, Level>;
  /** Number of puzzles in a round; 1 for a single puzzle. */
  roundSize: number;
  /** Starts a round that picks its puzzles the way `plan` says. */
  start: (plan: Plan) => void;
  select: (value: number) => void;
  /** Sends the selected answer to the server. Does nothing without one. */
  check: () => void;
  /** Fetches the next hint tier for the current step. */
  requestHint: () => void;
  /** Clears the answer of the current step. */
  reset: () => void;
  /**
   * After a solved puzzle: the next one. After the round: back to the start
   * screen. For a single puzzle: whatever its `solved.onNext` does.
   */
  next: () => void;
  /** On the error screen: do the thing that failed again. */
  retry: () => void;
  /** No answer can be changed right now (a check is running or the step is done). */
  locked: boolean;
  canHint: boolean;
}

export function usePuzzleSession<G extends GameId, Plan, Level>(
  config: PuzzleSessionConfig<G, Plan, Level>,
  timing: SessionTiming = DEFAULT_TIMING,
  single?: SinglePuzzle<G, Level>,
): PuzzleSession<G, Plan, Level> {
  const [state, dispatch] = useReducer(reducer<PuzzleOf<G>, Plan, Level>, single, initialState);

  // The callbacks below run after awaits, so they read the latest state from a ref.
  // A layout effect, not a plain one: the ref has to change together with the
  // page. Otherwise there is a moment when the next step is on screen while the
  // ref still says the last one is being marked, and a click then is dropped.
  const latest = useRef(state);
  // The single puzzle too: it may be built anew on every render.
  const singleRef = useRef(single);
  useLayoutEffect(() => {
    latest.current = state;
    singleRef.current = single;
  });
  // A single puzzle is fetched again at most once (see SinglePuzzle.reload).
  const reloaded = useRef(false);

  // One controller for the game's lifetime: leaving the game cancels whatever is in flight.
  const abort = useRef<AbortController | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const failed = useRef<Retry<Plan> | null>(null);
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

  const fail = useCallback((retry: Retry<Plan>) => {
    failed.current = retry;
    dispatch({ type: 'failed' });
  }, []);

  const loadPuzzle = useCallback(
    async (plan: Plan, puzzleIndex: number) => {
      const signal = abort.current?.signal;
      // When the backend decides, the level shown stays the last one until the answer is in.
      const known = config.fixedLevel(plan) ?? latest.current.level;
      dispatch({ type: 'loading', plan, level: known, puzzleIndex });

      let recommended: NextPuzzle | null = null;
      if (config.asksBackend(plan)) {
        recommended = await getNextPuzzle(config.game, signal);
        if (!alive()) return;
        // For adults and for development. Never shown to the child.
        if (import.meta.env.DEV) console.debug(`[${config.game}] next`, recommended);
      }

      const { level, request } = config.choose(plan, puzzleIndex, recommended);
      const result = await newPuzzle(config.game, request, signal);
      if (!alive()) return;
      if (result.status === 'ok') dispatch({ type: 'loaded', puzzle: result.data, level });
      else fail({ kind: 'load', plan, puzzleIndex });
    },
    [config, fail],
  );

  /** The single puzzle, fetched again. On "Try again" after a failed reload, too. */
  const reloadSingle = useCallback(async () => {
    const single = singleRef.current;
    if (!single) return;
    dispatch({ type: 'reloading' });
    const result = await single.reload(abort.current?.signal);
    if (!alive()) return;
    if (result.status === 'ok') {
      dispatch({ type: 'loaded', puzzle: result.data, level: single.level });
    } else {
      fail({ kind: 'reload' });
    }
  }, [fail]);

  /**
   * What every call about an existing puzzle does when it does not succeed.
   * A puzzle from an older generator version is replaced by a fresh one,
   * picked the same way, without a word; anything else shows the friendly error.
   * A single puzzle is fetched again instead, and only once.
   */
  const handleFailure = useCallback(
    (result: ApiResult<unknown>, retry: Retry<Plan>) => {
      const { plan, puzzleIndex } = latest.current;
      if (result.status === 'gone') {
        if (singleRef.current) {
          if (!reloaded.current) {
            reloaded.current = true;
            void reloadSingle();
            return;
          }
        } else if (plan !== null) {
          void loadPuzzle(plan, puzzleIndex);
          return;
        }
      }
      fail(retry);
    },
    [fail, loadPuzzle, reloadSingle],
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
    const result = await checkStep(
      puzzle.puzzle_id,
      stepIndex,
      selected,
      abort.current?.signal,
      singleRef.current?.context,
    );
    if (!alive()) return;
    if (result.status !== 'ok') {
      handleFailure(result, { kind: 'check' });
      return;
    }

    const { correct, diagnosis, next_step: nextStep } = result.data;
    // For later (adaptive practice). Never shown to the child.
    if (import.meta.env.DEV) console.debug(`[${config.game}] diagnosis`, diagnosis);

    if (!correct) {
      dispatch({ type: 'incorrect', diagnosis });
      // On the second wrong try a hint opens by itself, but never the last
      // tier: that one shows the answer, and the child has to ask for it.
      const totalTiers = config.hintTiers(puzzle, stepIndex);
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
      const single = singleRef.current;
      single?.onSolved?.();
      // A single puzzle is 'solved', not 'complete': there is no round to celebrate.
      const lastPuzzle = !single && puzzleIndex === config.roundSize - 1;
      timer.current = window.setTimeout(
        () => dispatch({ type: 'finished', feedback: lastPuzzle ? 'complete' : 'solved' }),
        timing.finishMs,
      );
    }
  }, [config, fetchHint, handleFailure, timing.advanceMs, timing.finishMs]);

  const locked = state.checking || state.feedback === 'correct' || state.phase !== 'playing';
  const totalTiers = state.puzzle ? config.hintTiers(state.puzzle, state.stepIndex) : 0;
  const canHint = !locked && !state.hintLoading && state.hintTier < totalTiers;

  const select = useCallback((value: number) => {
    const { checking, feedback, phase } = latest.current;
    if (phase === 'playing' && !checking && feedback !== 'correct') {
      dispatch({ type: 'selected', value });
    }
  }, []);

  const requestHint = useCallback(() => {
    const { puzzle, stepIndex, hintTier, hintLoading } = latest.current;
    const tiers = puzzle ? config.hintTiers(puzzle, stepIndex) : 0;
    if (!hintLoading && hintTier < tiers) void fetchHint(hintTier + 1);
  }, [config, fetchHint]);

  const next = useCallback(() => {
    const single = singleRef.current;
    if (single) {
      single.solved.onNext();
      return;
    }
    const { plan, puzzleIndex, feedback } = latest.current;
    if (plan === null || feedback === 'complete') dispatch({ type: 'restarted' });
    else void loadPuzzle(plan, puzzleIndex + 1);
  }, [loadPuzzle]);

  const retry = useCallback(() => {
    const again = failed.current;
    if (again === null) return;
    failed.current = null;
    if (again.kind === 'load') {
      void loadPuzzle(again.plan, again.puzzleIndex);
      return;
    }
    if (again.kind === 'reload') {
      void reloadSingle();
      return;
    }
    // The puzzle is still there: go back to it, then repeat the call.
    dispatch({ type: 'resumed' });
    if (again.kind === 'check') void check();
    else void fetchHint(again.tier);
  }, [check, fetchHint, loadPuzzle, reloadSingle]);

  return {
    state,
    roundSize: single ? 1 : config.roundSize,
    start: useCallback((plan: Plan) => void loadPuzzle(plan, 0), [loadPuzzle]),
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
