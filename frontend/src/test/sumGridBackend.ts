import { http, HttpResponse, type HttpHandler } from 'msw';
import type { components } from '../api/schema';

/*
 * A pretend puzzle API for the Sum Grid tests, built on MSW. It answers the
 * same routes as the real backend with bodies typed from openapi.json, so a
 * change to the API's shape breaks these fixtures at compile time.
 *
 * One fixture per level. The grids, options and hints are what the real
 * generator makes for such grids.
 */

type Schemas = components['schemas'];
type SumGridPublic = Schemas['SumGridPublic'];
type CheckResult = Schemas['CheckResult'];
type Diagnosis = Schemas['DiagnosisPublic'];

export interface FixtureStep {
  cell: Schemas['Cell'];
  line: Schemas['Line'];
  options: number[];
  hints: [string, string, string];
  /** Wrong answers the server recognizes as a known mistake. */
  mistakes: Record<number, Diagnosis>;
}

export interface GridFixture {
  /** The whole grid, answers included. Only the fixture knows them. */
  grid: number[][];
  rowTargets: number[];
  colTargets: number[];
  steps: FixtureStep[];
}

const diagnosis = (rule: string, reteach: Diagnosis['reteach_topic'] = null): Diagnosis => ({
  matched_rules: [rule],
  unrecognized: false,
  reteach_topic: reteach,
});
const EQUALS_SIGN = { id: 'mt_oIzycTBeE4', name: 'What the equals sign means' };

/**
 * Level 1, the example from the spec.
 *   3 | □ |  9
 *   □ | 5 |  7
 *   5  11
 */
export const TWO_BY_TWO: GridFixture = {
  grid: [
    [3, 6],
    [2, 5],
  ],
  rowTargets: [9, 7],
  colTargets: [5, 11],
  steps: [
    {
      cell: { row: 0, col: 1 },
      line: { kind: 'row', index: 0 },
      options: [12, 8, 6, 7],
      hints: [
        'Look at the top row. Only one number is missing there.',
        'The top row must make 9. The other number is 3. What do you add to 3 to make 9?',
        '9 − 3 = 6, so the missing number is 6.',
      ],
      mistakes: { 12: diagnosis('ADD_VISIBLE', EQUALS_SIGN), 8: diagnosis('WRONG_LINE') },
    },
    {
      cell: { row: 1, col: 0 },
      line: { kind: 'row', index: 1 },
      options: [12, 0, 2, 3],
      hints: [
        'Look at the bottom row. Only one number is missing there.',
        'The bottom row must make 7. The other number is 5. What do you add to 5 to make 7?',
        '7 − 5 = 2, so the missing number is 2.',
      ],
      mistakes: { 12: diagnosis('ADD_VISIBLE', EQUALS_SIGN) },
    },
  ],
};

/**
 * Level 2. The first blank is solved from its column, the others from rows.
 *   □ | □ | 9 | 16
 *   4 | □ | 8 | 15
 *   7 | 6 | 1 | 14
 *  13  14  18
 */
export const THREE_BY_THREE: GridFixture = {
  grid: [
    [2, 5, 9],
    [4, 3, 8],
    [7, 6, 1],
  ],
  rowTargets: [16, 15, 14],
  colTargets: [13, 14, 18],
  steps: [
    {
      cell: { row: 0, col: 0 },
      line: { kind: 'col', index: 0 },
      options: [24, 6, 2, 5],
      hints: [
        'Look at the left column. Only one number is missing there.',
        'The left column must make 13. The other numbers make 11. What do you add to 11 to make 13?',
        '13 − 11 = 2, so the missing number is 2.',
      ],
      mistakes: { 24: diagnosis('ADD_VISIBLE', EQUALS_SIGN), 6: diagnosis('FORGOT_ONE') },
    },
    {
      cell: { row: 0, col: 1 },
      line: { kind: 'row', index: 0 },
      options: [27, 7, 5, 3],
      hints: [
        'Look at the top row. Only one number is missing there.',
        'The top row must make 16. The other numbers make 11. What do you add to 11 to make 16?',
        '16 − 11 = 5, so the missing number is 5.',
      ],
      mistakes: { 27: diagnosis('ADD_VISIBLE', EQUALS_SIGN) },
    },
    {
      cell: { row: 1, col: 1 },
      line: { kind: 'row', index: 1 },
      options: [27, 7, 3, 2],
      hints: [
        'Look at the middle row. Only one number is missing there.',
        'The middle row must make 15. The other numbers make 12. What do you add to 12 to make 15?',
        '15 − 12 = 3, so the missing number is 3.',
      ],
      mistakes: { 27: diagnosis('ADD_VISIBLE', EQUALS_SIGN) },
    },
  ],
};

/**
 * Level 3, two-digit cells, targets up to 89.
 *   20 | 37 |  □ | 85
 *    □ | 40 | 22 | 77
 *   31 |  □ |  □ | 73
 *   66   89   80
 */
export const BIG_NUMBERS: GridFixture = {
  grid: [
    [20, 37, 28],
    [15, 40, 22],
    [31, 12, 30],
  ],
  rowTargets: [85, 77, 73],
  colTargets: [66, 89, 80],
  steps: [
    {
      cell: { row: 0, col: 2 },
      line: { kind: 'row', index: 0 },
      options: [32, 46, 28, 142],
      hints: [
        'Look at the top row. Only one number is missing there.',
        'The top row must make 85. The other numbers make 57. What do you add to 57 to make 85?',
        '85 − 57 = 28, so the missing number is 28.',
      ],
      mistakes: { 32: diagnosis('PLACE_VALUE_SLIP'), 46: diagnosis('TENS_AS_ONES') },
    },
    {
      cell: { row: 1, col: 0 },
      line: { kind: 'row', index: 1 },
      options: [51, 139, 15, 37],
      hints: [
        'Look at the middle row. Only one number is missing there.',
        'The middle row must make 77. The other numbers make 62. What do you add to 62 to make 77?',
        '77 − 62 = 15, so the missing number is 15.',
      ],
      mistakes: { 51: diagnosis('TENS_AS_ONES') },
    },
    {
      cell: { row: 2, col: 1 },
      line: { kind: 'col', index: 1 },
      options: [48, 166, 12, 49],
      hints: [
        'Look at the middle column. Only one number is missing there.',
        'The middle column must make 89. The other numbers make 77. What do you add to 77 to make 89?',
        '89 − 77 = 12, so the missing number is 12.',
      ],
      mistakes: { 48: diagnosis('TENS_AS_ONES') },
    },
    {
      cell: { row: 2, col: 2 },
      line: { kind: 'row', index: 2 },
      options: [116, 42, 30, 37],
      hints: [
        'Look at the bottom row. Only one number is missing there.',
        'The bottom row must make 73. The other numbers make 43. What do you add to 43 to make 73?',
        '73 − 43 = 30, so the missing number is 30.',
      ],
      mistakes: { 116: diagnosis('ADD_VISIBLE', EQUALS_SIGN) },
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

export interface SumGridBackend {
  handlers: HttpHandler[];
  /** The fixture each level hands out. Swap one to play another grid. */
  byLevel: Record<number, GridFixture>;
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

export function createSumGridBackend(
  byLevel: Record<number, GridFixture> = { 1: TWO_BY_TWO, 2: THREE_BY_THREE, 3: BIG_NUMBERS },
): SumGridBackend {
  const puzzles = new Map<string, { level: number; fixture: GridFixture }>();
  const pending: Record<Route, Failure[]> = { new: [], get: [], check: [], hint: [] };
  let counter = 0;

  const backend: SumGridBackend = {
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

  const toPublic = (puzzleId: string, level: number, fixture: GridFixture): SumGridPublic => {
    const blanks = new Set(fixture.steps.map((step) => `${step.cell.row},${step.cell.col}`));
    return {
      game: 'sum-grid',
      puzzle_id: puzzleId,
      level,
      size: fixture.grid.length,
      length: fixture.steps.length,
      topic_ids: ['mt_3JgrHY221M'],
      cells: fixture.grid.map((row, r) =>
        row.map((value, c) => (blanks.has(`${r},${c}`) ? null : value)),
      ),
      row_targets: fixture.rowTargets,
      col_targets: fixture.colTargets,
      steps: fixture.steps.map((step, index) => ({
        index,
        cell: step.cell,
        line: step.line,
        options: step.options,
        hint_tiers: step.hints.length,
      })),
    };
  };

  backend.handlers = [
    http.post('*/api/v1/puzzles/sum-grid', async ({ request }) => {
      const body = (await request.json()) as Schemas['NewSumGridRequest'];
      backend.requests.new.push(body as Record<string, unknown>);
      await pause();
      const failure = pending.new.shift();
      if (failure !== undefined) return failureResponse(failure);
      const fixture = backend.byLevel[body.level];
      if (!fixture) return failureResponse(404);
      counter += 1;
      const puzzleId = `sg-1-${body.level}-${counter}-test`;
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
      const step = fixture?.steps[index];
      if (failure !== undefined) return failureResponse(failure);
      if (!fixture || !step) return failureResponse(404);
      const correct = answer === fixture.grid[step.cell.row]?.[step.cell.col];
      const result: CheckResult = {
        correct,
        feedback: correct ? 'correct' : 'try_again',
        diagnosis: correct ? NO_DIAGNOSIS : (step.mistakes[answer] ?? UNRECOGNIZED),
        next_step: correct && index < fixture.steps.length - 1 ? index + 1 : null,
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
      const text = puzzles.get(puzzleId)?.fixture.steps[index]?.hints[tier - 1];
      if (failure !== undefined) return failureResponse(failure);
      if (text === undefined) return failureResponse(404);
      const hint: Schemas['HintOut'] = { tier, text };
      return HttpResponse.json(hint);
    }),
  ];

  return backend;
}
