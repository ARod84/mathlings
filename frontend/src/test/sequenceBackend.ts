import { http, HttpResponse, type HttpHandler } from 'msw';
import type { components } from '../api/schema';

/*
 * A pretend puzzle API for the "Next in Line" tests, built on MSW. It answers
 * the same routes as the real backend with bodies typed from openapi.json, so
 * a change to the API's shape breaks these fixtures at compile time.
 *
 * One fixture per level, and a growing-step one to swap in. The numbers,
 * options and hints are what the real generator makes for such rows.
 */

type Schemas = components['schemas'];
type SequencePublic = Schemas['SequencePublic'];
type CheckResult = Schemas['CheckResult'];
type Diagnosis = Schemas['DiagnosisPublic'];

export interface FixtureBlank {
  /** Which term of the row is blank, from 0. */
  position: number;
  options: number[];
  hints: [string, string, string];
  /** Wrong answers the server recognizes as a known mistake. */
  mistakes: Record<number, Diagnosis>;
}

export interface SequenceFixture {
  /** The whole row, answers included. Only the fixture knows them. */
  terms: number[];
  blanks: FixtureBlank[];
}

const LOOK = 'Look at how much each number changes from one to the next.';

const diagnosis = (rule: string, reteach: Diagnosis['reteach_topic'] = null): Diagnosis => ({
  matched_rules: [rule],
  unrecognized: false,
  reteach_topic: reteach,
});

/** Level 1. 4, 8, 12, 16, □ */
export const COUNTING_ON: SequenceFixture = {
  terms: [4, 8, 12, 16, 20],
  blanks: [
    {
      position: 4,
      options: [17, 24, 20, 21],
      hints: [
        LOOK,
        'Each time it goes up by 4. What is 16 + 4?',
        '16 + 4 = 20, so the missing number is 20.',
      ],
      mistakes: { 17: diagnosis('COUNT_BY_ONE'), 24: diagnosis('SKIPPED_TERM') },
    },
  ],
};

/** Level 2, two blanks. 45, 35, 25, □, □ */
export const TWO_BLANKS: SequenceFixture = {
  terms: [45, 35, 25, 15, 5],
  blanks: [
    {
      position: 3,
      options: [35, 15, 24, 5],
      hints: [
        LOOK,
        'Each time it goes down by 10. What is 25 − 10?',
        '25 − 10 = 15, so the missing number is 15.',
      ],
      mistakes: { 35: diagnosis('WRONG_DIRECTION') },
    },
    {
      position: 4,
      options: [25, 14, 6, 5],
      hints: [
        LOOK,
        'Each time it goes down by 10. What is 15 − 10?',
        '15 − 10 = 5, so the missing number is 5.',
      ],
      mistakes: { 25: diagnosis('WRONG_DIRECTION') },
    },
  ],
};

/** Level 3, down through zero. 9, 6, 3, 0, □ */
export const THROUGH_ZERO: SequenceFixture = {
  terms: [9, 6, 3, 0, -3],
  blanks: [
    {
      position: 4,
      options: [0, -3, 3, -1],
      hints: [
        LOOK,
        'Keep going down by 3, past zero. The numbers below zero have a minus sign.',
        '0 − 3 = −3, so the missing number is −3.',
      ],
      mistakes: {
        0: diagnosis('STOPS_AT_ZERO', { id: 'mt_RVK655t391', name: 'Measuring temperature' }),
        3: diagnosis('SIGN_DROPPED'),
      },
    },
  ],
};

/** Level 3, a growing step. 1, 2, 4, 7, □ */
export const GROWING: SequenceFixture = {
  terms: [1, 2, 4, 7, 11],
  blanks: [
    {
      position: 4,
      options: [10, 8, 11, 16],
      hints: [
        LOOK,
        'The jumps get bigger by 1 each time: +1, +2, +3… How big is the jump into the box?',
        'The jump into the box is +4. 7 + 4 = 11, so the missing number is 11.',
      ],
      mistakes: { 10: diagnosis('CONSTANT_GAP') },
    },
  ],
};

/** Level 2, six terms with a blank in the middle. 50, □, 150, 200, 250, 300 */
export const MIDDLE_BLANK: SequenceFixture = {
  terms: [50, 100, 150, 200, 250, 300],
  blanks: [
    {
      position: 1,
      options: [51, 100, 150, 101],
      hints: [
        LOOK,
        'Each time it goes up by 50. What is 50 + 50?',
        '50 + 50 = 100, so the missing number is 100.',
      ],
      mistakes: {},
    },
  ],
};

export const UNRECOGNIZED: Diagnosis = {
  matched_rules: [],
  unrecognized: true,
  reteach_topic: null,
};
const NO_DIAGNOSIS: Diagnosis = { matched_rules: [], unrecognized: false, reteach_topic: null };

type Route = 'new' | 'get' | 'check' | 'hint';
/** A status code to answer with, or 'network' for no answer at all. */
type Failure = number | 'network';

export interface SequenceBackend {
  handlers: HttpHandler[];
  /** The fixture each level hands out. Swap one to play another row. */
  byLevel: Record<number, SequenceFixture>;
  /** Everything the app asked for, in order. */
  requests: {
    new: Record<string, unknown>[];
    get: string[];
    check: { puzzleId: string; step: number; answer: number }[];
    hint: { puzzleId: string; step: number; tier: number }[];
  };
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

export function createSequenceBackend(
  byLevel: Record<number, SequenceFixture> = { 1: COUNTING_ON, 2: TWO_BLANKS, 3: THROUGH_ZERO },
): SequenceBackend {
  const puzzles = new Map<string, { level: number; fixture: SequenceFixture }>();
  const pending: Record<Route, Failure[]> = { new: [], get: [], check: [], hint: [] };
  let counter = 0;

  const backend: SequenceBackend = {
    handlers: [],
    byLevel: { ...byLevel },
    requests: { new: [], get: [], check: [], hint: [] },
    failNext: (route, failure) => pending[route].push(failure),
    delayMs: 0,
  };

  const pause = () =>
    backend.delayMs > 0
      ? new Promise<void>((resolve) => setTimeout(resolve, backend.delayMs))
      : Promise.resolve();

  const toPublic = (puzzleId: string, level: number, fixture: SequenceFixture): SequencePublic => {
    const blanks = new Set(fixture.blanks.map((blank) => blank.position));
    return {
      game: 'sequences',
      puzzle_id: puzzleId,
      level,
      length: fixture.blanks.length,
      topic_ids: ['mt_W3VOAuFwVw'],
      terms: fixture.terms.map((term, position) => (blanks.has(position) ? null : term)),
      steps: fixture.blanks.map((blank, index) => ({
        index,
        position: blank.position,
        options: blank.options,
        hint_tiers: blank.hints.length,
      })),
    };
  };

  backend.handlers = [
    http.post('*/api/v1/puzzles/sequences', async ({ request }) => {
      const body = (await request.json()) as Schemas['NewSequenceRequest'];
      backend.requests.new.push(body as Record<string, unknown>);
      await pause();
      const failure = pending.new.shift();
      if (failure !== undefined) return failureResponse(failure);
      const fixture = backend.byLevel[body.level];
      if (!fixture) return failureResponse(404);
      counter += 1;
      const puzzleId = `seq-1-${body.level}-${counter}-test`;
      puzzles.set(puzzleId, { level: body.level, fixture });
      return HttpResponse.json(toPublic(puzzleId, body.level, fixture), { status: 201 });
    }),

    http.get('*/api/v1/puzzles/:puzzleId', async ({ params }) => {
      const puzzleId = String(params.puzzleId);
      backend.requests.get.push(puzzleId);
      await pause();
      const failure = pending.get.shift();
      const found = puzzles.get(puzzleId);
      if (failure !== undefined) return failureResponse(failure);
      if (!found) return failureResponse(404);
      return HttpResponse.json(toPublic(puzzleId, found.level, found.fixture));
    }),

    http.post('*/api/v1/puzzles/:puzzleId/steps/:index/check', async ({ params, request }) => {
      const puzzleId = String(params.puzzleId);
      const index = Number(params.index);
      const { answer } = (await request.json()) as Schemas['CheckRequest'];
      backend.requests.check.push({ puzzleId, step: index, answer });
      await pause();
      const failure = pending.check.shift();
      const fixture = puzzles.get(puzzleId)?.fixture;
      const blank = fixture?.blanks[index];
      if (failure !== undefined) return failureResponse(failure);
      if (!fixture || !blank) return failureResponse(404);
      const correct = answer === fixture.terms[blank.position];
      const result: CheckResult = {
        correct,
        feedback: correct ? 'correct' : 'try_again',
        diagnosis: correct ? NO_DIAGNOSIS : (blank.mistakes[answer] ?? UNRECOGNIZED),
        next_step: correct && index < fixture.blanks.length - 1 ? index + 1 : null,
      };
      return HttpResponse.json(result);
    }),

    http.get('*/api/v1/puzzles/:puzzleId/steps/:index/hints/:tier', async ({ params }) => {
      const puzzleId = String(params.puzzleId);
      const index = Number(params.index);
      const tier = Number(params.tier);
      backend.requests.hint.push({ puzzleId, step: index, tier });
      await pause();
      const failure = pending.hint.shift();
      const text = puzzles.get(puzzleId)?.fixture.blanks[index]?.hints[tier - 1];
      if (failure !== undefined) return failureResponse(failure);
      if (text === undefined) return failureResponse(404);
      const hint: Schemas['HintOut'] = { tier, text };
      return HttpResponse.json(hint);
    }),
  ];

  return backend;
}
