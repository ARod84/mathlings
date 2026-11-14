import { render, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextPuzzle } from '../api/player';
import { Home } from '../home/Home';
import { createDailyBackend, type DailyBackend } from '../test/dailyBackend';
import { createSequenceBackend } from '../test/sequenceBackend';
import { server } from '../test/server';
import { DailyBanner } from './DailyBanner';
import { RESTING } from './copy';
import { DAILY_KEY } from './progress';

/*
 * The "Today's Puzzle" banner on the home screen. 2026-03-09 is a Monday, so
 * Wednesday 11 March 2026 is the usual "today" here.
 */

const NO_POLICY: NextPuzzle = {
  level: 1,
  length: null,
  reason_code: 'no_policy',
  reason: 'for adults',
  focus_rule: null,
  focus: null,
  params: {},
  mastery: [],
};

let daily: DailyBackend;
/** What /next answers; a number is a failure status. */
let next: NextPuzzle | number;
let nextGames: (string | null)[];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 2, 11, 10, 30));
  daily = createDailyBackend('sequences', createSequenceBackend().issue);
  // Unless a test says otherwise, the backend cannot say what to play: no level is suggested.
  next = 503;
  nextGames = [];
  server.use(
    ...daily.handlers,
    http.get('*/api/v1/players/me/next', ({ request }) => {
      nextGames.push(new URL(request.url).searchParams.get('game'));
      if (typeof next === 'number') {
        return HttpResponse.json({ detail: 'Unavailable' }, { status: next });
      }
      return HttpResponse.json(next);
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

const banner = () => screen.getByRole('region', { name: 'Today’s Puzzle' });
const level = (name: string) => screen.getByRole('link', { name });
const levels = () =>
  within(screen.getByRole('group', { name: 'Today’s Puzzle levels' })).getAllByRole('link');
const dots = () => screen.getByTestId('week-dots');

describe('the banner', () => {
  it('shows the game of the day and the three levels, each a way in at its level', async () => {
    render(<DailyBanner />);

    expect(within(banner()).getByText('Today’s Puzzle')).toBeInTheDocument();
    await screen.findByRole('heading', { level: 2, name: 'Next in Line' });
    expect(levels().map((link) => link.getAttribute('aria-label'))).toEqual([
      'Easy',
      'Medium',
      'Hard',
    ]);
    expect(level('Easy')).toHaveAttribute('href', '#/daily/1');
    expect(level('Medium')).toHaveAttribute('href', '#/daily/2');
    expect(level('Hard')).toHaveAttribute('href', '#/daily/3');
    expect(screen.getByText(/Days played this week/)).toBeInTheDocument();
    expect(banner()).toHaveAttribute('data-status', 'ready');
  });

  it('sends the device’s local date, with level 1 to learn the game', async () => {
    render(<DailyBanner />);

    await waitFor(() => expect(daily.requests).toHaveLength(1));
    expect(daily.requests[0]).toEqual({ date: '2026-03-11', level: '1' });
  });

  it('sends the local date even at 23:30, when UTC is already tomorrow', async () => {
    const zone = process.env.TZ;
    // Buenos Aires: three hours behind UTC, all year.
    process.env.TZ = 'America/Argentina/Buenos_Aires';
    try {
      // 23:30 on 10 March in Buenos Aires is 02:30 on 11 March in UTC.
      vi.setSystemTime(new Date('2026-03-11T02:30:00Z'));
      expect(new Date().getHours()).toBe(23);
      expect(new Date().toISOString().slice(0, 10)).toBe('2026-03-11');

      render(<DailyBanner />);

      await waitFor(() => expect(daily.requests).toHaveLength(1));
      expect(daily.requests[0]?.date).toBe('2026-03-10');
    } finally {
      process.env.TZ = zone;
    }
  });

  it('marks the level /next suggests, subtly, without choosing it or hiding the others', async () => {
    next = { ...NO_POLICY, level: 2, reason_code: 'promote' };
    expect(NO_POLICY.level).toBe(1);
    render(<DailyBanner />);

    await screen.findByRole('link', { name: 'Medium, suggested' });
    expect(nextGames).toEqual(['sequences']);
    expect(level('Medium, suggested')).toHaveAttribute('data-suggested');
    expect(level('Easy')).not.toHaveAttribute('data-suggested');
    expect(level('Hard')).not.toHaveAttribute('data-suggested');
    expect(levels()).toHaveLength(3);
    for (const link of levels()) {
      expect(link).not.toHaveAttribute('aria-current');
      expect(link).not.toHaveAttribute('aria-pressed');
    }
  });

  it('marks nothing when /next has no answer', async () => {
    render(<DailyBanner />);

    await screen.findByRole('link', { name: 'Easy' });
    await waitFor(() => expect(nextGames).toHaveLength(1));
    expect(levels().map((link) => link.getAttribute('data-suggested'))).toEqual([null, null, null]);
  });

  it('shows a check mark on each level solved today, and the week’s dots', async () => {
    window.localStorage.setItem(
      DAILY_KEY,
      JSON.stringify({ '2026-03-09': [1], '2026-03-11': [1, 3], '2026-03-04': [2] }),
    );
    render(<DailyBanner />);

    await screen.findByRole('link', { name: 'Easy, solved' });
    expect(level('Easy, solved')).toHaveAttribute('data-solved');
    expect(level('Medium')).not.toHaveAttribute('data-solved');
    expect(level('Hard, solved')).toHaveAttribute('data-solved');
    // Monday and Wednesday this week; last Wednesday does not count.
    expect(dots()).toHaveTextContent('●○●○○○○');
    expect(dots()).toHaveAttribute('aria-label', '2 of 7: Monday, Wednesday');
    // All three stay playable.
    expect(levels()).toHaveLength(3);
  });

  it('shows seven empty dots on a fresh device', () => {
    render(<DailyBanner />);

    expect(dots()).toHaveTextContent('○○○○○○○');
    expect(dots()).toHaveAttribute('aria-label', 'none yet');
  });

  it('never says "streak", and nothing resets in words', async () => {
    window.localStorage.setItem(DAILY_KEY, JSON.stringify({ '2026-03-09': [1] }));
    const { container } = render(<Home />);

    await screen.findByRole('link', { name: 'Easy' });
    expect(container.textContent).not.toMatch(/streak/i);
    expect(container.innerHTML).not.toMatch(/streak/i);
    expect(container.textContent).not.toMatch(/in a row|missed|lost|reset/i);
  });

  it('rests when /daily fails, and the game cards still work', async () => {
    daily.failNext(503);
    render(<Home />);

    await screen.findByText(RESTING);
    expect(screen.queryByRole('group', { name: 'Today’s Puzzle levels' })).not.toBeInTheDocument();
    expect(nextGames).toEqual([]);
    expect(screen.getByRole('link', { name: 'Play Next in Line' })).toHaveAttribute(
      'href',
      '#/sequences',
    );
    expect(screen.getByRole('link', { name: 'Play Sum Grid' })).toBeInTheDocument();
    // The dots are the device's own; they do not need the server.
    expect(dots()).toBeInTheDocument();
  });

  it('rests on a network error too', async () => {
    daily.failNext('network');
    render(<DailyBanner />);

    await screen.findByText(RESTING);
  });
});
