import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { createDailyBackend, type DailyBackend } from '../test/dailyBackend';
import { CHAIN, createPuzzleBackend } from '../test/puzzleBackend';
import { createSequenceBackend, type SequenceBackend } from '../test/sequenceBackend';
import { server } from '../test/server';
import { createSumGridBackend, TWO_BY_TWO } from '../test/sumGridBackend';
import { COME_BACK, MORE_GAMES } from './copy';
import { DailyPuzzle } from './DailyPuzzle';
import { DAILY_KEY } from './progress';

/*
 * The #/daily/<level> screen. The day's game is Next in Line in most tests:
 * its level-1 fixture is 4, 8, 12, 16, □ with the answer 20.
 */

const FAST = { advanceMs: 20, finishMs: 20 };
type User = ReturnType<typeof userEvent.setup>;

let sequences: SequenceBackend;
let daily: DailyBackend;
let debug: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  // Wednesday 11 March 2026.
  vi.setSystemTime(new Date(2026, 2, 11, 10, 30));
  sequences = createSequenceBackend();
  daily = createDailyBackend('sequences', sequences.issue);
  server.use(
    ...sequences.handlers,
    ...daily.handlers,
    http.get('*/api/v1/players/me/next', () =>
      HttpResponse.json({
        level: 1,
        length: null,
        reason_code: 'no_policy',
        reason: 'for adults',
        focus_rule: null,
        focus: null,
        params: {},
        mastery: [],
      }),
    ),
  );
  debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
  window.location.hash = '';
});

afterEach(() => {
  debug.mockRestore();
  vi.useRealTimers();
  window.location.hash = '';
});

const shell = () => screen.getByRole('region', { name: 'Next in Line' });
const option = (name: string | number) =>
  within(screen.getByRole('group', { name: 'Answer choices' })).getByRole('button', {
    name: String(name),
  });
const action = (name: 'Hint' | 'Check' | 'Reset') => screen.getByRole('button', { name });

async function answer(user: User, value: number) {
  await user.click(option(value));
  await user.click(action('Check'));
}

describe('the daily screen', () => {
  it('asks for the device’s date at the level in the address, and starts the game on it', async () => {
    render(<DailyPuzzle level={2} onExit={vi.fn()} timing={FAST} />);

    await screen.findByTestId('sequence-row');
    expect(daily.requests).toEqual([{ date: '2026-03-11', level: '2' }]);
    // No start screen, no round: straight into the one puzzle.
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
    expect(shell()).toHaveAttribute('data-house', 'scientists');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Which number is missing?');
    // Nothing was asked of the ordinary new-puzzle route.
    expect(sequences.requests.new).toEqual([]);
  });

  it('sends context "daily" with every check, and nothing extra otherwise', async () => {
    const user = userEvent.setup({ delay: null });
    render(<DailyPuzzle level={1} onExit={vi.fn()} timing={FAST} />);
    await screen.findByTestId('sequence-row');

    await answer(user, 17);
    await waitFor(() => expect(shell()).toHaveAttribute('data-feedback', 'incorrect'));
    await answer(user, 20);
    await waitFor(() => expect(sequences.requests.check).toHaveLength(2));

    expect(sequences.requests.check.map((request) => request.context)).toEqual(['daily', 'daily']);
    expect(sequences.requests.check.map((request) => request.answer)).toEqual([17, 20]);
  });

  it('on a solve: says to come back tomorrow, offers More games, and remembers the level', async () => {
    const user = userEvent.setup({ delay: null });
    const onExit = vi.fn();
    render(<DailyPuzzle level={1} onExit={onExit} timing={FAST} />);
    await screen.findByTestId('sequence-row');

    await answer(user, 20);
    const solved = await screen.findByTestId('solved-screen');

    expect(within(solved).getByRole('heading', { name: 'You did it!' })).toBeVisible();
    expect(within(solved).getByText(COME_BACK)).toBeVisible();
    expect(screen.queryByText('Puzzle solved. Great thinking!')).not.toBeInTheDocument();
    expect(screen.queryByTestId('round-complete-screen')).not.toBeInTheDocument();
    const more = within(solved).getByRole('button', { name: MORE_GAMES });
    expect(more).toHaveFocus();
    expect(JSON.parse(window.localStorage.getItem(DAILY_KEY) ?? '{}')).toEqual({
      '2026-03-11': [1],
    });

    await user.click(more);
    expect(onExit).toHaveBeenCalledTimes(1);
  });

  it('shows the friendly error when /daily fails, and Try again asks again', async () => {
    const user = userEvent.setup({ delay: null });
    daily.failNext('network');
    render(<DailyPuzzle level={3} onExit={vi.fn()} timing={FAST} />);

    const region = await screen.findByRole('region', { name: 'Today’s Puzzle' });
    await within(region).findByRole('button', { name: 'Try again' });
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Let’s try that again');

    await user.click(screen.getByRole('button', { name: 'Try again' }));

    await screen.findByTestId('sequence-row');
    expect(daily.requests.map((request) => request.level)).toEqual(['3', '3']);
  });

  it('on a 410, fetches the daily puzzle again once and plays on', async () => {
    const user = userEvent.setup({ delay: null });
    render(<DailyPuzzle level={1} onExit={vi.fn()} timing={FAST} />);
    await screen.findByTestId('sequence-row');
    const first = sequences.requests.check;

    sequences.failNext('check', 410);
    await answer(user, 20);

    await waitFor(() => expect(daily.requests).toHaveLength(2));
    await screen.findByTestId('sequence-row');
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    // The replacement puzzle is a fresh one: the row is back to its blank.
    await answer(user, 20);
    await screen.findByTestId('solved-screen');
    expect(first).toHaveLength(2);
    expect(sequences.requests.check[1]?.puzzleId).not.toBe(sequences.requests.check[0]?.puzzleId);
  });

  it('on a second 410, shows the friendly error instead of looping', async () => {
    const user = userEvent.setup({ delay: null });
    render(<DailyPuzzle level={1} onExit={vi.fn()} timing={FAST} />);
    await screen.findByTestId('sequence-row');

    sequences.failNext('check', 410);
    await answer(user, 20);
    await waitFor(() => expect(daily.requests).toHaveLength(2));
    await screen.findByTestId('sequence-row');
    sequences.failNext('check', 410);
    await answer(user, 20);

    await screen.findByRole('button', { name: 'Try again' });
    expect(daily.requests).toHaveLength(2);
  });

  it('plays the day’s game whichever it is: Missing Number Chains', async () => {
    const chains = createPuzzleBackend();
    daily.game = 'missing-number';
    server.use(...chains.handlers, ...createDailyBackend('missing-number', chains.issue).handlers);
    const user = userEvent.setup({ delay: null });
    render(<DailyPuzzle level={1} onExit={vi.fn()} timing={FAST} />);

    await screen.findByRole('list', { name: 'Steps' });
    expect(screen.getByRole('region', { name: 'Missing Number Chains' })).toHaveAttribute(
      'data-house',
      'navigators',
    );
    const [first] = CHAIN;
    if (!first) throw new Error('empty fixture chain');
    await answer(user, first.answer);
    await waitFor(() => expect(chains.requests.check).toHaveLength(1));
    expect(chains.requests.check[0]?.context).toBe('daily');
  });

  it('plays the day’s game whichever it is: Sum Grid', async () => {
    const grids = createSumGridBackend();
    server.use(...grids.handlers, ...createDailyBackend('sum-grid', grids.issue).handlers);
    const user = userEvent.setup({ delay: null });
    render(<DailyPuzzle level={1} onExit={vi.fn()} timing={FAST} />);

    const region = await screen.findByRole('region', { name: 'Sum Grid' });
    expect(region).toHaveAttribute('data-house', 'artisans');
    const [step] = TWO_BY_TWO.steps;
    if (!step) throw new Error('empty fixture grid');
    await answer(user, TWO_BY_TWO.grid[step.cell.row]?.[step.cell.col] ?? -1);
    await waitFor(() => expect(grids.requests.check).toHaveLength(1));
    expect(grids.requests.check[0]?.context).toBe('daily');
  });
});

describe('from the home screen and back', () => {
  async function goTo(hash: string) {
    await act(async () => {
      window.location.hash = hash;
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
  }

  it('a solve puts a check mark on the level and a dot on the day', async () => {
    const user = userEvent.setup({ delay: null });
    render(<App />);
    const dots = () => screen.getByTestId('week-dots');
    await screen.findByRole('link', { name: 'Easy, suggested' });
    expect(dots()).toHaveTextContent('○○○○○○○');

    await user.click(screen.getByRole('link', { name: 'Easy, suggested' }));
    await goTo('#/daily/1');
    await screen.findByTestId('sequence-row');
    // The daily screen is not a round of five.
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
    await answer(user, 20);
    // The app uses the real pause before the solved screen, a little over a second.
    await user.click(await screen.findByRole('button', { name: MORE_GAMES }, { timeout: 3000 }));
    await goTo('#/');

    await screen.findByRole('link', { name: 'Easy, solved, suggested' });
    expect(screen.getByRole('link', { name: 'Easy, solved, suggested' })).toHaveAttribute(
      'data-solved',
    );
    expect(screen.getByRole('link', { name: 'Medium' })).not.toHaveAttribute('data-solved');
    // Wednesday: the third dot.
    expect(dots()).toHaveTextContent('○○●○○○○');
    expect(dots()).toHaveAttribute('aria-label', '1 of 7: Wednesday');
    expect(document.body.textContent).not.toMatch(/streak/i);
  });

  it('#/daily without a level is level 1, and the game cards keep their own rounds', async () => {
    window.location.hash = '#/daily';
    render(<App />);

    await screen.findByTestId('sequence-row');
    expect(daily.requests[0]?.level).toBe('1');

    await goTo('#/sequences');
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(screen.getByText('0 / 5')).toBeInTheDocument();
  });
});
