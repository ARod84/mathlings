import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PLAYER_ID_KEY } from '../api/player';
import { App } from '../App';
import { MissingNumber } from '../games/missing-number/MissingNumber';
import { CHAIN, createPuzzleBackend, type PuzzleBackend } from '../test/puzzleBackend';
import { server } from '../test/server';
import { blockStorage } from '../test/storage';

const FORGET = 'Forget my progress on this device';
const FAST = { advanceMs: 20, finishMs: 20 };

let backend: PuzzleBackend;
let deleted: (string | null)[];
let deleteStatus: number;

beforeEach(() => {
  window.location.hash = '';
  backend = createPuzzleBackend();
  deleted = [];
  deleteStatus = 204;
  server.use(
    ...backend.handlers,
    http.delete('*/api/v1/players/me', ({ request }) => {
      deleted.push(request.headers.get('X-Player-Id'));
      return new HttpResponse(null, { status: deleteStatus });
    }),
  );
  vi.spyOn(console, 'debug').mockImplementation(() => {});
});

afterEach(() => {
  window.location.hash = '';
  vi.restoreAllMocks();
});

async function goTo(hash: string) {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

/** Opens Missing Number Chains from the home screen and starts a round. */
async function playOnePuzzleRequest(user: ReturnType<typeof userEvent.setup>) {
  await goTo('#/missing-number');
  await user.click(screen.getByRole('button', { name: 'Up to 20' }));
  await screen.findByRole('list', { name: 'Steps' });
  await goTo('#/');
}

describe('"Forget my progress" on the home screen', () => {
  it('is a quiet text button in the footer, and no request is made by showing it', () => {
    render(<App />);

    const footer = screen.getByRole('contentinfo');
    expect(within(footer).getByRole('button', { name: FORGET })).toBeInTheDocument();
    expect(deleted).toEqual([]);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBeNull();
  });

  it('asks first, inside the page, and "Keep it" changes nothing', async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, 'confirm');
    render(<App />);
    await playOnePuzzleRequest(user);
    const id = window.localStorage.getItem(PLAYER_ID_KEY);

    await user.click(screen.getByRole('button', { name: FORGET }));

    const question = screen.getByRole('group', { name: 'Forget my progress' });
    expect(within(question).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(deleted).toEqual([]);

    await user.click(within(question).getByRole('button', { name: 'Keep it' }));

    expect(screen.getByRole('button', { name: FORGET })).toBeInTheDocument();
    expect(deleted).toEqual([]);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBe(id);
    expect(confirm).not.toHaveBeenCalled();
  });

  it('calls DELETE, clears the key, and the next play carries a new id', async () => {
    const user = userEvent.setup();
    render(<App />);
    await playOnePuzzleRequest(user);
    const before = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(backend.playerIds).toEqual([before]);

    await user.click(screen.getByRole('button', { name: FORGET }));
    await user.click(screen.getByRole('button', { name: 'Yes, forget it' }));

    expect(await screen.findByText('Done. Your progress is forgotten.')).toBeInTheDocument();
    expect(deleted).toEqual([before]);
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBeNull();

    await playOnePuzzleRequest(user);

    const after = window.localStorage.getItem(PLAYER_ID_KEY);
    expect(after).not.toBeNull();
    expect(after).not.toBe(before);
    expect(backend.playerIds).toEqual([before, after]);
  });

  it('says so and keeps the id when the server cannot delete', async () => {
    const user = userEvent.setup();
    deleteStatus = 503;
    render(<App />);
    await playOnePuzzleRequest(user);
    const id = window.localStorage.getItem(PLAYER_ID_KEY);

    await user.click(screen.getByRole('button', { name: FORGET }));
    await user.click(screen.getByRole('button', { name: 'Yes, forget it' }));

    expect(await screen.findByText('That did not work. Please try again.')).toBeInTheDocument();
    expect(window.localStorage.getItem(PLAYER_ID_KEY)).toBe(id);
    expect(screen.getByRole('button', { name: FORGET })).toBeInTheDocument();
  });
});

describe('Missing Number Chains with localStorage blocked', () => {
  it('still plays, and no request carries a player id', async () => {
    blockStorage();
    const user = userEvent.setup();
    render(<MissingNumber timing={FAST} />);
    const shell = screen.getByRole('region', { name: 'Missing Number Chains' });

    await user.click(screen.getByRole('button', { name: 'Up to 20' }));
    await screen.findByRole('list', { name: 'Steps' });
    await user.click(screen.getByRole('button', { name: 'Hint' }));
    await screen.findByText(CHAIN[0]?.hints[0] ?? '');
    await user.click(screen.getByRole('button', { name: String(CHAIN[0]?.answer) }));
    await user.click(screen.getByRole('button', { name: 'Check' }));

    // Not the "correct" feedback: with FAST it lasts 20 ms, and the answer
    // comes back while the click above is still being awaited, so it can be
    // over before the test looks. The second step appearing is what lasts.
    const steps = within(screen.getByRole('list', { name: 'Steps' }));
    await waitFor(() => expect(steps.getAllByRole('listitem')).toHaveLength(2));
    expect(shell).toHaveAttribute('data-feedback', 'idle');
    expect(backend.requests.check).toHaveLength(1);
    expect(backend.requests.hint).toHaveLength(1);
    expect(backend.playerIds).toEqual([null, null, null]);
  });
});
