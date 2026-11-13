import { http, HttpResponse, type HttpHandler } from 'msw';
import type { components } from '../api/schema';

/*
 * A pretend puzzle API for tests, built on MSW. It answers the same four
 * routes as the real backend with bodies typed from openapi.json, so a change
 * to the API's shape breaks these fixtures at compile time.
 *
 * Every puzzle it hands out is the first `length` steps of CHAIN below.
 */

type Schemas = components['schemas'];
type PuzzlePublic = Schemas['PuzzlePublic'];
type CheckResult = Schemas['CheckResult'];
type Diagnosis = Schemas['DiagnosisPublic'];
type Token = Schemas['Equation']['left'][number];

const n = (value: number): Token => ({ kind: 'number', value });
const op = (symbol: '+' | '-'): Token => ({ kind: 'operator', symbol });
const box: Token = { kind: 'unknown' };

export interface FixtureStep {
  equation: Schemas['Equation'];
  options: number[];
  answer: number;
  hints: [string, string, string];
  /** Wrong answers the server recognizes as a known mistake. */
  mistakes: Record<number, Diagnosis>;
  /** Which token is the previous step's answer. Null on a first step. */
  linked: Schemas['LinkedToken'] | null;
}

const ADD_VISIBLE: Diagnosis = {
  matched_rules: ['ADD_VISIBLE'],
  unrecognized: false,
  reteach_topic: { id: 'mt_oIzycTBeE4', name: 'What the equals sign means' },
};

/** 8 + □ = 11,  □ − 3 = 5,  14 − □ = 8,  20 = 6 + □ */
export const CHAIN: FixtureStep[] = [
  {
    equation: { left: [n(8), op('+'), box], right: [n(11)] },
    options: [2, 3, 19, 4],
    answer: 3,
    hints: [
      'The = sign means both sides are worth the same.',
      'What number do you add to 8 to make 11? Try 11 − 8.',
      '11 − 8 = 3, so the missing number is 3. Check: 8 + 3 = 11.',
    ],
    mistakes: { 19: ADD_VISIBLE },
    linked: null,
  },
  {
    equation: { left: [box, op('-'), n(3)], right: [n(5)] },
    options: [9, 2, 8, 7],
    answer: 8,
    hints: [
      'The = sign means both sides are worth the same.',
      'A number take away 3 leaves 5. Put them back together: try 5 + 3.',
      '5 + 3 = 8, so the missing number is 8. Check: 8 − 3 = 5.',
    ],
    mistakes: {},
    linked: { side: 'left', index: 2 },
  },
  {
    equation: { left: [n(14), op('-'), box], right: [n(8)] },
    options: [6, 5, 7, 4],
    answer: 6,
    hints: [
      'The = sign means both sides are worth the same.',
      'What do you take away from 14 to leave 8? Try 14 − 8.',
      '14 − 8 = 6, so the missing number is 6. Check: 14 − 6 = 8.',
    ],
    mistakes: {},
    linked: { side: 'right', index: 0 },
  },
  {
    equation: { left: [n(20)], right: [n(6), op('+'), box] },
    options: [26, 13, 14, 15],
    answer: 14,
    hints: [
      'The = sign means both sides are worth the same. The answer does not have to come last.',
      '20 is the same as 6 plus what? Try 20 − 6.',
      '20 − 6 = 14, so the missing number is 14. Check: 6 + 14 = 20.',
    ],
    mistakes: { 26: ADD_VISIBLE },
    linked: { side: 'right', index: 0 },
  },
];

const PLAIN_HINTS: FixtureStep['hints'] = [
  'The = sign means both sides are worth the same.',
  'Try the inverse.',
  'Here is the worked step.',
];

/**
 * 14 − □ = 5 gives 9, then □ − 9 = 9: both visible numbers of the second step
 * are 9, and the link is the one on the right of the equals sign.
 */
export const SAME_VALUE_TWICE: FixtureStep[] = [
  {
    equation: { left: [n(14), op('-'), box], right: [n(5)] },
    options: [8, 9, 19, 10],
    answer: 9,
    hints: PLAIN_HINTS,
    mistakes: {},
    linked: null,
  },
  {
    equation: { left: [box, op('-'), n(9)], right: [n(9)] },
    options: [17, 18, 0, 19],
    answer: 18,
    hints: PLAIN_HINTS,
    mistakes: {},
    linked: { side: 'right', index: 0 },
  },
];

export const UNRECOGNIZED: Diagnosis = {
  matched_rules: [],
  unrecognized: true,
  reteach_topic: null,
};
const NO_DIAGNOSIS: Diagnosis = { matched_rules: [], unrecognized: false, reteach_topic: null };

type Route = 'new' | 'get' | 'check' | 'hint';
/** A status code to answer with, or 'network' for no answer at all. */
type Failure = number | 'network';

export interface PuzzleBackend {
  handlers: HttpHandler[];
  /** Everything the app asked for, in order. */
  requests: {
    new: { level: number; length: number; seed?: number | null; focus?: string | null }[];
    get: string[];
    check: { puzzleId: string; step: number; answer: number }[];
    hint: { puzzleId: string; step: number; tier: number }[];
  };
  /** The JSON body of every new-puzzle request, exactly as it was sent. */
  newBodies: Record<string, unknown>[];
  /** The X-Player-Id header of every request, in order; null where there was none. */
  playerIds: (string | null)[];
  /** Make the next call to a route fail once. */
  failNext: (route: Route, failure: Failure) => void;
  /** Hold every answer back by this many milliseconds. */
  delayMs: number;
}

function failureResponse(failure: Failure): Response {
  if (failure === 'network') return HttpResponse.error();
  if (failure === 410) {
    return HttpResponse.json(
      { detail: 'Puzzle version is no longer available', current_version: '1' },
      { status: 410 },
    );
  }
  if (failure === 404) {
    return HttpResponse.json({ detail: 'Puzzle not found', puzzle_id: 'x' }, { status: 404 });
  }
  return HttpResponse.json({ detail: 'Unavailable' }, { status: failure });
}

/** `chain` is the steps every puzzle is cut from; CHAIN unless a test needs another. */
export function createPuzzleBackend(chain: FixtureStep[] = CHAIN): PuzzleBackend {
  const puzzles = new Map<string, FixtureStep[]>();
  const pending: Record<Route, Failure[]> = { new: [], get: [], check: [], hint: [] };
  let counter = 0;

  const backend: PuzzleBackend = {
    handlers: [],
    requests: { new: [], get: [], check: [], hint: [] },
    newBodies: [],
    playerIds: [],
    failNext: (route, failure) => pending[route].push(failure),
    delayMs: 0,
  };

  const seen = (request: Request) => backend.playerIds.push(request.headers.get('X-Player-Id'));

  const pause = () =>
    backend.delayMs > 0
      ? new Promise<void>((resolve) => setTimeout(resolve, backend.delayMs))
      : Promise.resolve();

  const toPublic = (puzzleId: string, level: number, steps: FixtureStep[]): PuzzlePublic => ({
    game: 'missing-number',
    puzzle_id: puzzleId,
    level,
    length: steps.length,
    topic_ids: ['mt_3JgrHY221M'],
    steps: steps.map((step, index) => ({
      index,
      equation: step.equation,
      options: step.options,
      hint_tiers: step.hints.length,
      linked_token: step.linked,
    })),
  });

  backend.handlers = [
    http.post('*/api/v1/puzzles/missing-number', async ({ request }) => {
      seen(request);
      const body = (await request.json()) as Schemas['NewPuzzleRequest'];
      backend.newBodies.push(body as Record<string, unknown>);
      backend.requests.new.push({
        level: body.level,
        length: body.length ?? 3,
        seed: body.seed,
        focus: body.focus,
      });
      await pause();
      const failure = pending.new.shift();
      if (failure !== undefined) return failureResponse(failure);
      counter += 1;
      const steps = chain.slice(0, body.length ?? 3);
      const puzzleId = `mnc-1-${body.level}-${steps.length}-${counter}-test`;
      puzzles.set(puzzleId, steps);
      return HttpResponse.json(toPublic(puzzleId, body.level, steps), { status: 201 });
    }),

    http.get('*/api/v1/puzzles/:puzzleId', async ({ params, request }) => {
      seen(request);
      const puzzleId = String(params.puzzleId);
      backend.requests.get.push(puzzleId);
      await pause();
      const failure = pending.get.shift();
      const steps = puzzles.get(puzzleId);
      if (failure !== undefined) return failureResponse(failure);
      if (!steps) return failureResponse(404);
      return HttpResponse.json(toPublic(puzzleId, Number(puzzleId.split('-')[2]), steps));
    }),

    http.post('*/api/v1/puzzles/:puzzleId/steps/:index/check', async ({ params, request }) => {
      seen(request);
      const puzzleId = String(params.puzzleId);
      const index = Number(params.index);
      const { answer } = (await request.json()) as Schemas['CheckRequest'];
      backend.requests.check.push({ puzzleId, step: index, answer });
      await pause();
      const failure = pending.check.shift();
      const steps = puzzles.get(puzzleId);
      const step = steps?.[index];
      if (failure !== undefined) return failureResponse(failure);
      if (!steps || !step) return failureResponse(404);
      const correct = answer === step.answer;
      const result: CheckResult = {
        correct,
        feedback: correct ? 'correct' : 'try_again',
        diagnosis: correct ? NO_DIAGNOSIS : (step.mistakes[answer] ?? UNRECOGNIZED),
        next_step: correct && index < steps.length - 1 ? index + 1 : null,
      };
      return HttpResponse.json(result);
    }),

    http.get('*/api/v1/puzzles/:puzzleId/steps/:index/hints/:tier', async ({ params, request }) => {
      seen(request);
      const puzzleId = String(params.puzzleId);
      const index = Number(params.index);
      const tier = Number(params.tier);
      backend.requests.hint.push({ puzzleId, step: index, tier });
      await pause();
      const failure = pending.hint.shift();
      const text = puzzles.get(puzzleId)?.[index]?.hints[tier - 1];
      if (failure !== undefined) return failureResponse(failure);
      if (text === undefined) return failureResponse(404);
      const hint: Schemas['HintOut'] = { tier, text };
      return HttpResponse.json(hint);
    }),
  ];

  return backend;
}
