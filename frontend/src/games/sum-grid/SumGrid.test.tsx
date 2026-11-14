import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextPuzzle } from '../../api/player';
import {
  BIG_NUMBERS,
  createSumGridBackend,
  THREE_BY_THREE,
  TWO_BY_TWO,
  type SumGridBackend,
} from '../../test/sumGridBackend';
import { server } from '../../test/server';
import { SumGrid } from './SumGrid';
import { ROUND_SIZE } from './useSumGridGame';

// Short pauses, so a whole round plays in well under a second.
const FAST = { advanceMs: 20, finishMs: 20 };

type User = ReturnType<typeof userEvent.setup>;

/** What the backend says for a game that has no policy yet. */
const NO_POLICY: NextPuzzle = {
  level: 1,
  length: null,
  reason_code: 'no_policy',
  reason: 'sum-grid has no recommendation policy yet, so this is its default.',
  focus_rule: null,
  focus: null,
  params: {},
  mastery: [],
};

let backend: SumGridBackend;
let debug: ReturnType<typeof vi.spyOn>;
let next: NextPuzzle | number;
let nextGames: (string | null)[];

beforeEach(() => {
  backend = createSumGridBackend();
  next = NO_POLICY;
  nextGames = [];
  server.use(
    ...backend.handlers,
    http.get('*/api/v1/players/me/next', ({ request }) => {
      nextGames.push(new URL(request.url).searchParams.get('game'));
      if (typeof next === 'number') {
        return HttpResponse.json({ detail: 'Unavailable' }, { status: next });
      }
      return HttpResponse.json(next);
    }),
  );
  debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
});

afterEach(() => {
  debug.mockRestore();
});

const shell = () => screen.getByRole('region', { name: 'Sum Grid' });
const feedback = () => shell().getAttribute('data-feedback');
const grid = () => screen.getByTestId('sum-grid');
const rows = () => within(grid()).getAllByRole('row');
/** The blocks of the grid, row by row, as their states ("given", "blank", ...) or "target". */
const states = () =>
  rows().map((row) =>
    Array.from(row.querySelectorAll('span')).map(
      (block) => block.getAttribute('data-state') ?? block.getAttribute('data-kind'),
    ),
  );
const currentBlank = () => {
  const current = grid().querySelector('[aria-current="step"]');
  if (!current) throw new Error('no current blank');
  return current as HTMLElement;
};
const highlightedCells = () => Array.from(grid().querySelectorAll('td[data-highlighted]'));
const options = () => within(screen.getByRole('group', { name: 'Answer choices' }));
const option = (value: number) => options().getByRole('button', { name: String(value) });
const action = (name: 'Hint' | 'Check' | 'Reset') => screen.getByRole('button', { name });

/** Renders the game and starts a round at the level with this label. */
async function start(user: User, label = '2 by 2', timing = FAST) {
  const view = render(<SumGrid timing={timing} />);
  await user.click(screen.getByRole('button', { name: label }));
  await screen.findByTestId('sum-grid');
  return view;
}

/** Picks an option and checks it. */
async function answer(user: User, value: number) {
  await user.click(option(value));
  await user.click(action('Check'));
}

describe('start screen', () => {
  it('offers Play and the three levels by name, and nothing else to do yet', () => {
    render(<SumGrid />);

    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    const levels = within(screen.getByRole('group', { name: 'Or choose a level' }));
    expect(levels.getAllByRole('button').map((button) => button.textContent)).toEqual([
      '2 by 2',
      '3 by 3',
      'Big numbers',
    ]);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Ready to make the sums add up?',
    );
    expect(screen.getByText(`0 / ${ROUND_SIZE}`)).toBeInTheDocument();
    expect(shell()).toHaveAttribute('data-house', 'artisans');
    for (const name of ['Hint', 'Check', 'Reset'] as const) expect(action(name)).toBeDisabled();
    expect(backend.requests.new).toEqual([]);
  });

  it.each([
    ['2 by 2', 1],
    ['3 by 3', 2],
    ['Big numbers', 3],
  ])('"%s" asks for a level %i puzzle and does not ask what to play', async (label, level) => {
    const user = userEvent.setup();
    await start(user, label);

    expect(backend.requests.new).toEqual([{ level }]);
    expect(nextGames).toEqual([]);
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
  });

  it('"Play" asks the backend about sum-grid and plays the level it says', async () => {
    const user = userEvent.setup();
    render(<SumGrid timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sum-grid');

    expect(nextGames).toEqual(['sum-grid']);
    expect(backend.requests.new).toEqual([{ level: 1 }]);
    expect(document.body).not.toHaveTextContent('no_policy');
    expect(document.body).not.toHaveTextContent(NO_POLICY.reason);
  });

  it('"Play" falls back to level 1 without a word when the backend cannot say', async () => {
    const user = userEvent.setup();
    next = 503;
    render(<SumGrid timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sum-grid');

    expect(backend.requests.new).toEqual([{ level: 1 }]);
  });
});

describe('a 2 by 2 puzzle', () => {
  it('draws the grid with its targets, the current blank highlighted and the other muted', async () => {
    const user = userEvent.setup();
    await start(user);

    // 3 | □ | 9  over  □ | 5 | 7, then the column targets 5, 11.
    expect(states()).toEqual([
      ['given', 'current', 'target'],
      ['blank', 'given', 'target'],
      ['target', 'target'],
    ]);
    expect(rows()[0]?.textContent).toBe('39');
    expect(rows()[2]?.textContent).toBe('511');
    expect(currentBlank()).toHaveAccessibleName('Row 1, column 2. Blank 1 of 2.');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(TWO_BY_TWO.steps[0]?.options.map(String));
    expect(action('Check')).toBeDisabled();
    expect(highlightedCells()).toEqual([]);
  });

  it('is solved blank by blank, each filling in and locking', async () => {
    const user = userEvent.setup();
    render(<SumGrid timing={{ advanceMs: 20, finishMs: 400 }} />);
    await user.click(screen.getByRole('button', { name: '2 by 2' }));
    await screen.findByTestId('sum-grid');

    await user.click(option(6));
    expect(currentBlank()).toHaveTextContent('6');
    expect(currentBlank()).toHaveAccessibleName('Row 1, column 2. Blank 1 of 2, with 6.');
    await user.click(action('Check'));

    await waitFor(() => expect(states()[0]).toEqual(['given', 'solved', 'target']));
    expect(states()[1]).toEqual(['current', 'given', 'target']);
    expect(currentBlank()).toHaveAccessibleName('Row 2, column 1. Blank 2 of 2.');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(TWO_BY_TWO.steps[1]?.options.map(String));

    await answer(user, 2);

    await waitFor(() => expect(states()[1]).toEqual(['solved', 'given', 'target']));
    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check.map(({ step, answer: given }) => [step, given])).toEqual([
      [0, 6],
      [1, 2],
    ]);
    expect(await screen.findByTestId('solved-screen')).toBeInTheDocument();
  });

  it('swaps the pick, and Reset empties the blank', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(12));
    await user.click(option(8));
    expect(currentBlank()).toHaveTextContent('8');
    await user.click(action('Reset'));
    expect(currentBlank()).toHaveTextContent('');
    expect(action('Check')).toBeDisabled();
  });
});

describe('a 3 by 3 puzzle', () => {
  it('is solved in the server order, solved cells locking, with focus following', async () => {
    const user = userEvent.setup();
    await start(user, '3 by 3');

    // □ | □ | 9 over 4 | □ | 8 over 7 | 6 | 1: the first blank is solved from its column.
    expect(states()).toEqual([
      ['current', 'blank', 'given', 'target'],
      ['given', 'blank', 'given', 'target'],
      ['given', 'given', 'given', 'target'],
      ['target', 'target', 'target'],
    ]);
    expect(currentBlank()).toHaveAccessibleName('Row 1, column 1. Blank 1 of 3.');

    await answer(user, 2);
    await waitFor(() =>
      expect(currentBlank()).toHaveAccessibleName('Row 1, column 2. Blank 2 of 3.'),
    );
    expect(states()[0]).toEqual(['solved', 'current', 'given', 'target']);
    expect(rows()[0]?.textContent).toBe('2916');
    await waitFor(() => expect(currentBlank()).toHaveFocus());

    await answer(user, 5);
    await waitFor(() =>
      expect(currentBlank()).toHaveAccessibleName('Row 2, column 2. Blank 3 of 3.'),
    );
    expect(states()[0]).toEqual(['solved', 'solved', 'given', 'target']);
    expect(states()[1]).toEqual(['given', 'current', 'given', 'target']);

    await answer(user, 3);
    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check.map(({ step, answer: given }) => [step, given])).toEqual([
      [0, 2],
      [1, 5],
      [2, 3],
    ]);
  });

  it('a wrong answer leaves the solved cells locked and the pick in the blank', async () => {
    const user = userEvent.setup();
    await start(user, '3 by 3');
    await answer(user, 2);
    await waitFor(() =>
      expect(currentBlank()).toHaveAccessibleName('Row 1, column 2. Blank 2 of 3.'),
    );

    await answer(user, 27);

    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(states()[0]).toEqual(['solved', 'current', 'given', 'target']);
    expect(currentBlank()).toHaveTextContent('27');
  });

  it('shows two-digit cells and targets up to three digits at level 3', async () => {
    const user = userEvent.setup();
    await start(user, 'Big numbers');

    expect(rows()[0]?.textContent).toBe('203785');
    expect(rows()[3]?.textContent).toBe('668980');
    expect(currentBlank()).toHaveAccessibleName('Row 1, column 3. Blank 1 of 4.');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(BIG_NUMBERS.steps[0]?.options.map(String));
  });
});

describe('the line highlight', () => {
  it('is off before the first hint, and lights the whole line after it', async () => {
    const user = userEvent.setup();
    await start(user, '3 by 3');
    expect(highlightedCells()).toEqual([]);

    await user.click(action('Hint'));
    await screen.findByText(THREE_BY_THREE.steps[0]?.hints[0] as string);

    // The first blank is solved from the left column: its three cells and the column's target.
    const lit = highlightedCells();
    expect(lit).toHaveLength(4);
    expect(lit.map((cell) => cell.textContent)).toEqual(['', '4', '7', '13']);
    expect(lit[0]).toBe(currentBlank());
    expect(lit[3]).toHaveAccessibleName('Target 13');
  });

  it('lights a row with its target at the right end', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(action('Hint'));
    await screen.findByText(TWO_BY_TWO.steps[0]?.hints[0] as string);

    expect(highlightedCells().map((cell) => cell.textContent)).toEqual(['3', '', '9']);
    expect(highlightedCells()[2]).toHaveAccessibleName('Target 9');
  });

  it('stays for the rest of the step and goes with the next blank', async () => {
    const user = userEvent.setup();
    await start(user);
    await user.click(action('Hint'));
    await screen.findByText(TWO_BY_TWO.steps[0]?.hints[0] as string);
    await user.click(action('Hint'));
    await screen.findByText(TWO_BY_TWO.steps[0]?.hints[1] as string);
    expect(highlightedCells()).toHaveLength(3);

    await answer(user, 6);
    await waitFor(() =>
      expect(currentBlank()).toHaveAccessibleName('Row 2, column 1. Blank 2 of 2.'),
    );

    expect(highlightedCells()).toEqual([]);
  });

  it('is not announced on its own: the hint text already says which line', async () => {
    const user = userEvent.setup();
    await start(user);
    const before = document.querySelectorAll('[aria-live]').length;

    await user.click(action('Hint'));
    await screen.findByText('Look at the top row. Only one number is missing there.');

    expect(document.querySelectorAll('[aria-live]')).toHaveLength(before);
    expect(screen.getAllByText(/Look at the top row/)).toHaveLength(1);
  });
});

describe('wrong answers and hints', () => {
  it('a wrong answer is marked incorrect; two wrong tries open a hint and the line', async () => {
    const user = userEvent.setup();
    await start(user);

    await answer(user, 12);
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(backend.requests.hint).toEqual([]);
    expect(highlightedCells()).toEqual([]);

    await answer(user, 8);

    expect(await screen.findByText(TWO_BY_TWO.steps[0]?.hints[0] as string)).toBeInTheDocument();
    expect(backend.requests.hint).toEqual([{ puzzleId: 'sg-1-1-1-test', step: 0, tier: 1 }]);
    expect(highlightedCells()).toHaveLength(3);
  });

  it('gives the tiers in order, 1 then 2 then 3, and then no more', async () => {
    const user = userEvent.setup();
    await start(user);

    for (const [index, text] of (TWO_BY_TWO.steps[0]?.hints ?? []).entries()) {
      await user.click(action('Hint'));
      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(backend.requests.hint.at(-1)?.tier).toBe(index + 1);
    }
    expect(action('Hint')).toBeDisabled();
  });

  it('never shows the diagnosis, and logs it for development only', async () => {
    const user = userEvent.setup();
    await start(user);

    await answer(user, 12);
    await waitFor(() => expect(feedback()).toBe('incorrect'));

    for (const secret of ['ADD_VISIBLE', 'What the equals sign means', 'mt_oIzycTBeE4']) {
      expect(document.body).not.toHaveTextContent(secret);
    }
    expect(debug).toHaveBeenCalledWith(
      '[sum-grid] diagnosis',
      expect.objectContaining({ matched_rules: ['ADD_VISIBLE'] }),
    );
  });
});

describe('the grid for a screen reader', () => {
  it('is a table with a description that reads row by row, before and after filling', async () => {
    const user = userEvent.setup();
    render(<SumGrid timing={{ advanceMs: 20, finishMs: 400 }} />);
    await user.click(screen.getByRole('button', { name: '2 by 2' }));
    await screen.findByTestId('sum-grid');

    const table = screen.getByRole('table', { name: 'Sum grid, 2 by 2' });
    expect(table).toHaveAccessibleDescription(
      'Row 1: 3, blank. Target 9. Row 2: blank, 5. Target 7. Column targets: 5, 11.',
    );
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    // A picked number is not part of the grid until it is right.
    await user.click(option(6));
    expect(table).toHaveAccessibleDescription(/Row 1: 3, blank\./);

    await user.click(action('Check'));

    await waitFor(() =>
      expect(table).toHaveAccessibleDescription(
        'Row 1: 3, 6. Target 9. Row 2: blank, 5. Target 7. Column targets: 5, 11.',
      ),
    );
  });

  it('names each target and each waiting blank, and the current blank with its place', async () => {
    const user = userEvent.setup();
    await start(user, '3 by 3');

    const cells = within(grid()).getAllByRole('cell');
    expect(cells.filter((cell) => cell.getAttribute('aria-label') === 'blank')).toHaveLength(2);
    expect(cells.map((cell) => cell.getAttribute('aria-label')).filter(Boolean)).toEqual([
      'Row 1, column 1. Blank 1 of 3.',
      'blank',
      'Target 16',
      'blank',
      'Target 15',
      'Target 14',
      'Target 13',
      'Target 14',
      'Target 18',
    ]);
    expect(currentBlank()).toHaveAttribute('aria-current', 'step');
  });
});

describe('keyboard', () => {
  it('keys 1 to 4 pick the options in order and Enter checks', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.keyboard('1');
    expect(currentBlank()).toHaveTextContent('12');
    await user.keyboard('3');
    expect(currentBlank()).toHaveTextContent('6');
    expect(option(6)).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('5');
    expect(currentBlank()).toHaveTextContent('6');

    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(backend.requests.check).toEqual([{ puzzleId: 'sg-1-1-1-test', step: 0, answer: 6 }]),
    );
  });

  it('Enter does nothing with no option picked', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.keyboard('{Enter}');

    expect(backend.requests.check).toEqual([]);
  });
});

describe('a round', () => {
  it('is five puzzles, and the fifth ends it', async () => {
    const user = userEvent.setup({ delay: null });
    await start(user);

    for (let puzzle = 1; puzzle <= ROUND_SIZE; puzzle += 1) {
      expect(screen.getByText(`${puzzle} / ${ROUND_SIZE}`)).toBeInTheDocument();
      await answer(user, 6);
      await waitFor(() => expect(currentBlank()).toHaveAccessibleName(/Blank 2 of 2/));
      await answer(user, 2);
      if (puzzle < ROUND_SIZE) {
        await user.click(
          await within(await screen.findByTestId('solved-screen')).findByRole('button'),
        );
        await waitFor(() =>
          expect(screen.getByText(`${puzzle + 1} / ${ROUND_SIZE}`)).toBeInTheDocument(),
        );
        await screen.findByTestId('sum-grid');
      }
    }

    const complete = await screen.findByTestId('round-complete-screen');
    expect(feedback()).toBe('complete');
    expect(backend.requests.new).toHaveLength(ROUND_SIZE);

    await user.click(within(complete).getByRole('button'));
    expect(await screen.findByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(screen.getByText(`0 / ${ROUND_SIZE}`)).toBeInTheDocument();
  });
});

describe('when something goes wrong', () => {
  it('a puzzle from an older version is replaced by a fresh one without a word', async () => {
    const user = userEvent.setup();
    await start(user);
    backend.failNext('check', 410);

    await answer(user, 6);

    await waitFor(() => expect(backend.requests.new).toHaveLength(2));
    await waitFor(() => expect(currentBlank()).toHaveTextContent(''));
    expect(feedback()).toBe('idle');
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.queryByText(/try again/i)).not.toBeInTheDocument();
    await answer(user, 6);
    await waitFor(() => expect(backend.requests.check.at(-1)?.puzzleId).toBe('sg-1-1-2-test'));
  });

  it('a network error on loading shows a friendly message, and Try again loads', async () => {
    const user = userEvent.setup();
    backend.failNext('new', 'network');
    render(<SumGrid timing={FAST} />);

    await user.click(screen.getByRole('button', { name: '2 by 2' }));

    expect(await screen.findByText(/couldn.t get your puzzle just now/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId('sum-grid')).toBeInTheDocument();
    expect(backend.requests.new).toHaveLength(2);
  });

  it('a network error on checking keeps the pick, and Try again checks it', async () => {
    const user = userEvent.setup();
    await start(user);
    backend.failNext('check', 'network');

    await answer(user, 6);
    await user.click(await screen.findByRole('button', { name: 'Try again' }));

    await waitFor(() =>
      expect(backend.requests.check.map((request) => request.answer)).toEqual([6, 6]),
    );
  });

  it('shows a calm placeholder while the puzzle loads', async () => {
    const user = userEvent.setup();
    backend.delayMs = 150;
    render(<SumGrid timing={FAST} />);

    await user.click(screen.getByRole('button', { name: '2 by 2' }));

    expect(screen.getByText('Loading your puzzle')).toBeInTheDocument();
    expect(await screen.findByTestId('sum-grid')).toBeInTheDocument();
  });
});
