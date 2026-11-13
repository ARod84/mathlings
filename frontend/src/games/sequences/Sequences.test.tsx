import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextPuzzle } from '../../api/player';
import {
  COUNTING_ON,
  createSequenceBackend,
  GROWING,
  MIDDLE_BLANK,
  THROUGH_ZERO,
  TWO_BLANKS,
  type SequenceBackend,
} from '../../test/sequenceBackend';
import { server } from '../../test/server';
import { Sequences } from './Sequences';
import { ROUND_SIZE } from './useSequencesGame';

// Short pauses, so a whole round plays in well under a second.
const FAST = { advanceMs: 20, finishMs: 20 };
const MINUS = '−';

type User = ReturnType<typeof userEvent.setup>;

/** What the backend says for a game that has no policy yet. */
const NO_POLICY: NextPuzzle = {
  level: 1,
  length: null,
  reason_code: 'no_policy',
  reason: 'sequences has no recommendation policy yet, so this is its default.',
  focus_rule: null,
  focus: null,
  params: {},
  mastery: [],
};

let backend: SequenceBackend;
let debug: ReturnType<typeof vi.spyOn>;
/** What /next answers. A number is a failure status. */
let next: NextPuzzle | number;
let nextGames: (string | null)[];

beforeEach(() => {
  backend = createSequenceBackend();
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

const shell = () => screen.getByRole('region', { name: 'Next in Line' });
const feedback = () => shell().getAttribute('data-feedback');
const row = () => screen.getByTestId('sequence-row');
const blocks = () => within(row()).getAllByRole('listitem');
const states = () => blocks().map((block) => block.getAttribute('data-state'));
const currentBlank = () => {
  const current = blocks().find((block) => block.getAttribute('aria-current') === 'step');
  if (!current) throw new Error('no current blank');
  return current;
};
const options = () => within(screen.getByRole('group', { name: 'Answer choices' }));
const option = (name: string | number) => options().getByRole('button', { name: String(name) });
const action = (name: 'Hint' | 'Check' | 'Reset') => screen.getByRole('button', { name });
const arcs = () => screen.queryByTestId('jump-arcs');
const arcLabels = () =>
  Array.from(arcs()?.children ?? []).map((arc) => [
    Number(arc.getAttribute('data-from')),
    arc.textContent,
  ]);

/** Renders the game and starts a round at the level with this label. */
async function start(user: User, label = 'Counting on') {
  const view = render(<Sequences timing={FAST} />);
  await user.click(screen.getByRole('button', { name: label }));
  await screen.findByTestId('sequence-row');
  return view;
}

/** Picks an option and checks it. */
async function answer(user: User, name: string | number) {
  await user.click(option(name));
  await user.click(action('Check'));
}

describe('start screen', () => {
  it('offers Play and the three levels by name, and nothing else to do yet', () => {
    render(<Sequences />);

    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    const levels = within(screen.getByRole('group', { name: 'Or choose a level' }));
    expect(levels.getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Counting on',
      'Skip counting',
      'Tricky patterns',
    ]);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Ready to spot some patterns?',
    );
    expect(screen.getByText(`0 / ${ROUND_SIZE}`)).toBeInTheDocument();
    expect(shell()).toHaveAttribute('data-house', 'scientists');
    for (const name of ['Hint', 'Check', 'Reset'] as const) expect(action(name)).toBeDisabled();
    expect(backend.requests.new).toEqual([]);
  });

  it.each([
    ['Counting on', 1],
    ['Skip counting', 2],
    ['Tricky patterns', 3],
  ])('"%s" asks for a level %i puzzle and does not ask what to play', async (label, level) => {
    const user = userEvent.setup();
    await start(user, label);

    // A sequence has no parameters: the body is the level and nothing else.
    expect(backend.requests.new).toEqual([{ level }]);
    expect(nextGames).toEqual([]);
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Which number is missing?');
  });

  it('"Play" asks the backend about sequences and plays the level it says', async () => {
    const user = userEvent.setup();
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sequence-row');

    expect(nextGames).toEqual(['sequences']);
    // Today that is "no policy, level 1". The game just plays what it is told.
    expect(backend.requests.new).toEqual([{ level: 1 }]);
    expect(row()).toHaveAccessibleName('4, 8, 12, 16, blank');
  });

  it('"Play" follows another level as soon as the backend recommends one', async () => {
    const user = userEvent.setup();
    next = { ...NO_POLICY, level: 3, reason_code: 'consolidate' };
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sequence-row');

    expect(backend.requests.new).toEqual([{ level: 3 }]);
  });

  it('"Play" falls back to level 1 without a word when the backend cannot say', async () => {
    const user = userEvent.setup();
    next = 503;
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sequence-row');

    expect(backend.requests.new).toEqual([{ level: 1 }]);
    expect(screen.queryByText(/policy|recommend/i)).not.toBeInTheDocument();
  });

  it('never shows what the backend says about its recommendation', async () => {
    const user = userEvent.setup();
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Play' }));
    await screen.findByTestId('sequence-row');

    expect(document.body).not.toHaveTextContent('no_policy');
    expect(document.body).not.toHaveTextContent(NO_POLICY.reason);
  });
});

describe('a puzzle with one blank', () => {
  it('shows the row as blocks, the blank empty and highlighted, and four options', async () => {
    const user = userEvent.setup();
    await start(user);

    expect(blocks().map((block) => block.textContent)).toEqual(['4', '8', '12', '16', '']);
    expect(states()).toEqual(['given', 'given', 'given', 'given', 'current']);
    expect(currentBlank()).toHaveAccessibleName('Blank 1 of 1');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(COUNTING_ON.blanks[0]?.options.map(String));
    expect(action('Check')).toBeDisabled();
    expect(arcs()).not.toBeInTheDocument();
  });

  it('is solved by picking the right option and checking', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(20));
    expect(currentBlank()).toHaveTextContent('20');
    expect(currentBlank()).toHaveAttribute('data-filled');
    expect(option(20)).toHaveAttribute('aria-pressed', 'true');
    await user.click(action('Check'));

    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check).toEqual([{ puzzleId: 'seq-1-1-1-test', step: 0, answer: 20 }]);
    expect(await screen.findByTestId('solved-screen')).toBeInTheDocument();
  });

  it('fills the blank in and locks it once it is right', async () => {
    const user = userEvent.setup({ delay: null });
    backend.delayMs = 0;
    // Long enough to look at the row while "correct" is showing.
    render(<Sequences timing={{ advanceMs: 20, finishMs: 400 }} />);
    await user.click(screen.getByRole('button', { name: 'Counting on' }));
    await screen.findByTestId('sequence-row');

    await answer(user, 20);

    await waitFor(() => expect(states()).toEqual(['given', 'given', 'given', 'given', 'solved']));
    expect(blocks().at(-1)).toHaveTextContent('20');
    for (const button of options().getAllByRole('button')) expect(button).toBeDisabled();
  });

  it('swaps the pick, and Reset empties the blank', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.click(option(17));
    await user.click(option(24));
    expect(currentBlank()).toHaveTextContent('24');
    expect(option(17)).toHaveAttribute('aria-pressed', 'false');

    await user.click(action('Reset'));
    expect(currentBlank()).toBeEmptyDOMElement();
    expect(action('Check')).toBeDisabled();
  });
});

describe('a puzzle with two blanks', () => {
  it('is solved left to right, the first blank locking before the second opens', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');

    // 45, 35, 25, □, □: the first blank is the current one, the second waits.
    expect(states()).toEqual(['given', 'given', 'given', 'current', 'blank']);
    expect(currentBlank()).toHaveAccessibleName('Blank 1 of 2');
    expect(blocks().at(-1)).toHaveAccessibleName('blank');
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(TWO_BLANKS.blanks[0]?.options.map(String));

    await answer(user, 15);

    await waitFor(() => expect(states()).toEqual(['given', 'given', 'given', 'solved', 'current']));
    // The first blank holds its number for good; the second is now the one to solve.
    expect(blocks()[3]).toHaveTextContent('15');
    expect(blocks()[3]).not.toHaveAttribute('aria-current');
    expect(currentBlank()).toHaveAccessibleName('Blank 2 of 2');
    expect(currentBlank()).toBeEmptyDOMElement();
    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(TWO_BLANKS.blanks[1]?.options.map(String));
    expect(feedback()).toBe('idle');

    await answer(user, 5);

    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check.map(({ step, answer: given }) => [step, given])).toEqual([
      [0, 15],
      [1, 5],
    ]);
  });

  it('moves focus to the next blank after a correct answer', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');

    await answer(user, 15);

    await waitFor(() => expect(currentBlank()).toHaveAccessibleName('Blank 2 of 2'));
    await waitFor(() => expect(currentBlank()).toHaveFocus());
  });

  it('moves focus to the solved screen after the last blank', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');
    await answer(user, 15);
    await waitFor(() => expect(currentBlank()).toHaveAccessibleName('Blank 2 of 2'));

    await answer(user, 5);

    const solved = await screen.findByTestId('solved-screen');
    await waitFor(() => expect(solved).toContainElement(document.activeElement as HTMLElement));
  });

  it('a wrong second answer leaves the first blank locked', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');
    await answer(user, 15);
    await waitFor(() => expect(currentBlank()).toHaveAccessibleName('Blank 2 of 2'));

    await answer(user, 25);

    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(states()).toEqual(['given', 'given', 'given', 'solved', 'current']);
    expect(blocks()[3]).toHaveTextContent('15');
    expect(currentBlank()).toHaveTextContent('25');
  });
});

describe('negative numbers', () => {
  it('shows a negative option with the real minus sign and reads it as "minus"', async () => {
    const user = userEvent.setup();
    await start(user, 'Tricky patterns');

    expect(
      options()
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['0', `${MINUS}3`, '3', `${MINUS}1`]);
    expect(option('minus 3')).toHaveTextContent('−3');
    expect(option('minus 3').textContent).not.toContain('-');
    expect(option('minus 1')).toBeInTheDocument();
    // A positive tile needs no spoken form.
    expect(option(3)).not.toHaveAttribute('aria-label');
  });

  it('shows a negative answer in the row with U+2212 and the aria text "minus 3"', async () => {
    const user = userEvent.setup();
    render(<Sequences timing={{ advanceMs: 20, finishMs: 400 }} />);
    await user.click(screen.getByRole('button', { name: 'Tricky patterns' }));
    await screen.findByTestId('sequence-row');
    expect(row()).toHaveAccessibleName('9, 6, 3, 0, blank');

    await user.click(option('minus 3'));
    expect(currentBlank()).toHaveTextContent('−3');
    expect(currentBlank()).toHaveAccessibleName('Blank 1 of 1, with minus 3');
    await user.click(action('Check'));

    await waitFor(() => expect(states().at(-1)).toBe('solved'));
    const solved = blocks().at(-1) as HTMLElement;
    expect(solved.textContent).toBe(`${MINUS}3`);
    expect(solved).toHaveAccessibleName('minus 3');
    expect(row()).toHaveAccessibleName('9, 6, 3, 0, minus 3');
    // The server is sent the number, not its text.
    expect(backend.requests.check[0]?.answer).toBe(-3);
  });

  it('shows a negative given term the same way', async () => {
    const user = userEvent.setup();
    backend.byLevel[3] = {
      terms: [3, 0, -3, -6, -9],
      blanks: [
        { ...(THROUGH_ZERO.blanks[0] as (typeof THROUGH_ZERO.blanks)[number]), position: 4 },
      ],
    };
    await start(user, 'Tricky patterns');

    expect(blocks().map((block) => block.textContent)).toEqual([
      '3',
      '0',
      `${MINUS}3`,
      `${MINUS}6`,
      '',
    ]);
    expect(blocks()[2]).toHaveAccessibleName('minus 3');
    expect(row()).toHaveAccessibleName('3, 0, minus 3, minus 6, blank');
    expect(row().textContent).not.toContain('-');
  });
});

describe('the row for a screen reader', () => {
  it('reads naturally before and after the blank is filled', async () => {
    const user = userEvent.setup();
    backend.byLevel[2] = MIDDLE_BLANK;
    render(<Sequences timing={{ advanceMs: 20, finishMs: 400 }} />);
    await user.click(screen.getByRole('button', { name: 'Skip counting' }));
    await screen.findByTestId('sequence-row');

    expect(row()).toHaveAccessibleName('50, blank, 150, 200, 250, 300');
    // A number that is only picked is not part of the row yet.
    await user.click(option(100));
    expect(row()).toHaveAccessibleName('50, blank, 150, 200, 250, 300');
    expect(currentBlank()).toHaveAccessibleName('Blank 1 of 1, with 100');

    await user.click(action('Check'));
    await waitFor(() => expect(row()).toHaveAccessibleName('50, 100, 150, 200, 250, 300'));
  });

  it('announces which blank is current', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');

    expect(currentBlank()).toHaveAccessibleName('Blank 1 of 2');
    expect(currentBlank()).toHaveAttribute('aria-current', 'step');
    expect(row()).toHaveAccessibleName('45, 35, 25, blank, blank');
  });
});

describe('wrong answers and hints', () => {
  it('a wrong answer is marked incorrect and the pick stays in the blank', async () => {
    const user = userEvent.setup();
    await start(user);

    await answer(user, 17);

    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(currentBlank()).toHaveTextContent('17');
    expect(states().at(-1)).toBe('current');
    expect(backend.requests.hint).toEqual([]);
  });

  it('opens a hint by itself after two wrong tries', async () => {
    const user = userEvent.setup();
    await start(user);

    await answer(user, 17);
    await waitFor(() => expect(feedback()).toBe('incorrect'));
    expect(screen.queryByText('ORBI’s hint')).not.toBeInTheDocument();
    await answer(user, 24);

    expect(await screen.findByText(COUNTING_ON.blanks[0]?.hints[0] as string)).toBeInTheDocument();
    expect(backend.requests.hint).toEqual([{ puzzleId: 'seq-1-1-1-test', step: 0, tier: 1 }]);
    // The first tier only says where to look: no arcs yet.
    expect(arcs()).not.toBeInTheDocument();
  });

  it('gives the tiers in order, 1 then 2 then 3, and then no more', async () => {
    const user = userEvent.setup();
    await start(user);

    for (const [index, text] of (COUNTING_ON.blanks[0]?.hints ?? []).entries()) {
      await user.click(action('Hint'));
      expect(await screen.findByText(text)).toBeInTheDocument();
      expect(backend.requests.hint.at(-1)?.tier).toBe(index + 1);
    }
    expect(action('Hint')).toBeDisabled();
  });

  it('never shows the diagnosis, and logs it for development only', async () => {
    const user = userEvent.setup();
    await start(user, 'Tricky patterns');

    await answer(user, 0);
    await waitFor(() => expect(feedback()).toBe('incorrect'));

    for (const secret of ['STOPS_AT_ZERO', 'Measuring temperature', 'mt_RVK655t391']) {
      expect(document.body).not.toHaveTextContent(secret);
    }
    expect(debug).toHaveBeenCalledWith(
      '[sequences] diagnosis',
      expect.objectContaining({ matched_rules: ['STOPS_AT_ZERO'] }),
    );
  });
});

describe('jump arcs', () => {
  /** Fetches hint tiers one after another, up to `tier`. */
  async function hintUpTo(user: User, tier: number, hints: readonly string[]) {
    for (let index = 0; index < tier; index += 1) {
      await user.click(action('Hint'));
      await screen.findByText(hints[index] as string);
    }
  }

  it('appear after hint tier 2, one per pair of neighbouring visible numbers', async () => {
    const user = userEvent.setup();
    await start(user);

    await hintUpTo(user, 1, COUNTING_ON.blanks[0]?.hints ?? []);
    expect(arcs()).not.toBeInTheDocument();
    await user.click(action('Hint'));

    await waitFor(() => expect(arcs()).toBeInTheDocument());
    // 4, 8, 12, 16, □
    expect(arcLabels()).toEqual([
      [0, '+4'],
      [1, '+4'],
      [2, '+4'],
    ]);
  });

  it('no arc touches a blank', async () => {
    const user = userEvent.setup();
    backend.byLevel[2] = MIDDLE_BLANK;
    await start(user, 'Skip counting');
    await hintUpTo(user, 2, MIDDLE_BLANK.blanks[0]?.hints ?? []);
    await waitFor(() => expect(arcs()).toBeInTheDocument());

    // 50, □, 150, 200, 250, 300: the blank is the second block.
    const blankAt = states().indexOf('current');
    expect(blankAt).toBe(1);
    const touched = arcLabels().flatMap(([from]) => [from, (from as number) + 1]);
    expect(touched).not.toContain(blankAt);
    expect(arcLabels()).toEqual([
      [2, '+50'],
      [3, '+50'],
      [4, '+50'],
    ]);
    // And nowhere do the arcs say the missing number.
    expect(arcs()).not.toHaveTextContent('100');
  });

  it('no arc touches either of two blanks, solved or not', async () => {
    const user = userEvent.setup();
    await start(user, 'Skip counting');
    await hintUpTo(user, 2, TWO_BLANKS.blanks[0]?.hints ?? []);
    await waitFor(() => expect(arcs()).toBeInTheDocument());

    // 45, 35, 25, □, □
    expect(arcLabels()).toEqual([
      [0, `${MINUS}10`],
      [1, `${MINUS}10`],
    ]);

    // Solve the first blank and ask for the second blank's rule: still nothing
    // next to either blank, though the first one now shows its number.
    await answer(user, 15);
    await waitFor(() => expect(currentBlank()).toHaveAccessibleName('Blank 2 of 2'));
    expect(arcs()).not.toBeInTheDocument();
    await hintUpTo(user, 2, TWO_BLANKS.blanks[1]?.hints ?? []);
    await waitFor(() => expect(arcs()).toBeInTheDocument());
    expect(arcLabels().map(([from]) => from)).toEqual([0, 1]);
  });

  it('label each jump of a growing sequence with its own size', async () => {
    const user = userEvent.setup();
    backend.byLevel[3] = GROWING;
    await start(user, 'Tricky patterns');
    await hintUpTo(user, 2, GROWING.blanks[0]?.hints ?? []);

    await waitFor(() => expect(arcs()).toBeInTheDocument());
    // 1, 2, 4, 7, □
    expect(arcLabels()).toEqual([
      [0, '+1'],
      [1, '+2'],
      [2, '+3'],
    ]);
    // The jump into the blank (+4) is not drawn.
    expect(arcs()).not.toHaveTextContent('+4');
  });

  it('label a jump going down with the real minus sign', async () => {
    const user = userEvent.setup();
    await start(user, 'Tricky patterns');
    await hintUpTo(user, 2, THROUGH_ZERO.blanks[0]?.hints ?? []);

    await waitFor(() => expect(arcs()).toBeInTheDocument());
    expect(arcLabels().map(([, label]) => label)).toEqual(['−3', '−3', '−3']);
    expect(arcs()?.textContent).not.toContain('-');
  });

  it('are decoration: hidden from screen readers, and the row reads the same', async () => {
    const user = userEvent.setup();
    await start(user);
    const before = row().getAttribute('aria-label');
    await hintUpTo(user, 2, COUNTING_ON.blanks[0]?.hints ?? []);

    await waitFor(() => expect(arcs()).toBeInTheDocument());
    expect(arcs()).toHaveAttribute('aria-hidden', 'true');
    expect(row()).toHaveAccessibleName(before as string);
    expect(within(row()).getAllByRole('listitem')).toHaveLength(5);
  });

  it('stay for tier 3 and go when the puzzle is done', async () => {
    const user = userEvent.setup();
    await start(user);
    await hintUpTo(user, 3, COUNTING_ON.blanks[0]?.hints ?? []);
    expect(arcs()).toBeInTheDocument();

    await answer(user, 20);
    await user.click(await screen.findByRole('button', { name: /next/i }));
    await waitFor(() => expect(screen.getByText('2 / 5')).toBeInTheDocument());
    await screen.findByTestId('sequence-row');

    expect(arcs()).not.toBeInTheDocument();
  });
});

describe('keyboard', () => {
  it('keys 1 to 4 pick the options in order and Enter checks', async () => {
    const user = userEvent.setup();
    await start(user);

    await user.keyboard('1');
    expect(currentBlank()).toHaveTextContent('17');
    await user.keyboard('3');
    expect(currentBlank()).toHaveTextContent('20');
    expect(option(20)).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('5');
    expect(currentBlank()).toHaveTextContent('20');

    await user.keyboard('{Enter}');

    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check).toEqual([{ puzzleId: 'seq-1-1-1-test', step: 0, answer: 20 }]);
  });

  it('a key can pick a negative option', async () => {
    const user = userEvent.setup();
    await start(user, 'Tricky patterns');

    await user.keyboard('2');
    expect(currentBlank()).toHaveTextContent('−3');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(backend.requests.check[0]?.answer).toBe(-3));
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
      await answer(user, 20);
      if (puzzle < ROUND_SIZE) {
        await user.click(
          await within(await screen.findByTestId('solved-screen')).findByRole('button'),
        );
        await waitFor(() =>
          expect(screen.getByText(`${puzzle + 1} / ${ROUND_SIZE}`)).toBeInTheDocument(),
        );
        await screen.findByTestId('sequence-row');
      }
    }

    const complete = await screen.findByTestId('round-complete-screen');
    expect(feedback()).toBe('complete');
    expect(backend.requests.new).toHaveLength(ROUND_SIZE);
    expect(backend.requests.new.every((request) => request.level === 1)).toBe(true);

    // The button on the last screen goes back to the start.
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

    await answer(user, 20);

    await waitFor(() => expect(backend.requests.new).toHaveLength(2));
    await waitFor(() => expect(currentBlank()).toBeEmptyDOMElement());
    expect(feedback()).toBe('idle');
    expect(screen.getByText('1 / 5')).toBeInTheDocument();
    expect(screen.queryByText(/try again/i)).not.toBeInTheDocument();
    // The new puzzle is a new id, and it plays.
    await answer(user, 20);
    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check.at(-1)?.puzzleId).toBe('seq-1-1-2-test');
  });

  it('a network error on loading shows a friendly message, and Try again loads', async () => {
    const user = userEvent.setup();
    backend.failNext('new', 'network');
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Counting on' }));

    expect(await screen.findByText(/couldn.t get your puzzle just now/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Let’s try that again');
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId('sequence-row')).toBeInTheDocument();
    expect(backend.requests.new).toHaveLength(2);
  });

  it('a network error on checking keeps the pick, and Try again checks it', async () => {
    const user = userEvent.setup();
    await start(user);
    backend.failNext('check', 'network');

    await answer(user, 20);
    await user.click(await screen.findByRole('button', { name: 'Try again' }));

    await waitFor(() => expect(feedback()).toBe('solved'));
    expect(backend.requests.check.map((request) => request.answer)).toEqual([20, 20]);
  });

  it('leaving the game drops what is still on its way', async () => {
    const user = userEvent.setup();
    backend.delayMs = 60;
    const view = render(<Sequences timing={FAST} />);
    await user.click(screen.getByRole('button', { name: 'Counting on' }));

    view.unmount();
    await new Promise((resolve) => setTimeout(resolve, 120));

    expect(screen.queryByTestId('sequence-row')).not.toBeInTheDocument();
  });

  it('shows a calm placeholder while the puzzle loads', async () => {
    const user = userEvent.setup();
    backend.delayMs = 150;
    render(<Sequences timing={FAST} />);

    await user.click(screen.getByRole('button', { name: 'Counting on' }));

    expect(screen.getByText('Loading your puzzle')).toBeInTheDocument();
    expect(await screen.findByTestId('sequence-row')).toBeInTheDocument();
  });
});
