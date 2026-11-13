import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { GAMES, gameFor } from './games/registry';
import { parseRoute, ROUTE_HASH } from './router';
import { createPuzzleBackend } from './test/puzzleBackend';
import { server } from './test/server';

/** Sets the hash the way a link or the address bar would. */
async function goTo(hash: string) {
  await act(async () => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

beforeEach(() => {
  window.location.hash = '';
});

afterEach(() => {
  window.location.hash = '';
});

const cards = () => within(screen.getByRole('list', { name: 'Games' })).getAllByRole('listitem');

describe('home screen', () => {
  it('shows one card per game: title, one-line description and a Play link', () => {
    render(<App />);

    expect(screen.getByRole('heading', { level: 1, name: 'Mathlings' })).toBeInTheDocument();
    expect(cards()).toHaveLength(GAMES.length);
    for (const [index, game] of GAMES.entries()) {
      const card = within(cards()[index] as HTMLElement);
      expect(card.getByRole('heading', { level: 2, name: game.title })).toBeInTheDocument();
      expect(card.getByText(game.description)).toBeInTheDocument();
      expect(card.getByRole('link', { name: `Play ${game.title}` })).toHaveAttribute(
        'href',
        ROUTE_HASH[game.route],
      );
      expect(cards()[index]).toHaveAttribute('data-house', game.house);
    }
  });

  it('lists Number Pyramid and Missing Number Chains with their houses', () => {
    expect(GAMES.map((game) => [game.title, game.route, game.house])).toEqual([
      ['Number Pyramid', 'pyramid', 'builders'],
      ['Missing Number Chains', 'missing-number', 'navigators'],
    ]);
    expect(gameFor('missing-number').house).toBe('navigators');
    for (const game of GAMES) expect(game.description).not.toContain('\n');
  });
});

describe('routing', () => {
  it('goes home → Number Pyramid → back to home without reloading the page', async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    window.addEventListener('beforeunload', reload);
    render(<App />);

    await user.click(screen.getByRole('link', { name: 'Play Number Pyramid' }));
    await goTo(ROUTE_HASH.pyramid);

    const shell = screen.getByRole('region', { name: 'Number Pyramid' });
    expect(shell).toHaveAttribute('data-house', 'builders');
    expect(screen.queryByRole('list', { name: 'Games' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Back to games' }));

    await waitFor(() => expect(screen.getByRole('list', { name: 'Games' })).toBeInTheDocument());
    expect(window.location.hash).toBe('#/');
    expect(screen.queryByRole('region', { name: 'Number Pyramid' })).not.toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
    window.removeEventListener('beforeunload', reload);
  });

  it('goes home → Missing Number Chains → plays a step → back to home', async () => {
    const user = userEvent.setup();
    const backend = createPuzzleBackend();
    server.use(...backend.handlers);
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
    render(<App />);

    await goTo(ROUTE_HASH['missing-number']);
    const shell = screen.getByRole('region', { name: 'Missing Number Chains' });
    expect(shell).toHaveAttribute('data-house', 'navigators');

    await user.click(screen.getByRole('button', { name: 'Up to 20' }));
    await screen.findByRole('list', { name: 'Steps' });
    await user.click(screen.getByRole('button', { name: '3' }));
    await user.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() => expect(shell).toHaveAttribute('data-feedback', 'correct'));

    await user.click(screen.getByRole('button', { name: 'Back to games' }));

    await waitFor(() => expect(screen.getByRole('list', { name: 'Games' })).toBeInTheDocument());
    expect(screen.queryByRole('region', { name: 'Missing Number Chains' })).not.toBeInTheDocument();
    debug.mockRestore();
  });

  it('follows the hash when it changes, in both directions', async () => {
    render(<App />);
    expect(screen.getByRole('list', { name: 'Games' })).toBeInTheDocument();

    await goTo('#/pyramid');
    expect(screen.getByRole('region', { name: 'Number Pyramid' })).toBeInTheDocument();

    await goTo('#/');
    expect(screen.getByRole('list', { name: 'Games' })).toBeInTheDocument();

    await goTo('#shell-demo');
    expect(screen.getByRole('complementary', { name: 'Dev toolbar' })).toBeInTheDocument();
  });

  it('opens a game directly from its address', async () => {
    window.location.hash = '#/missing-number';
    render(<App />);

    expect(screen.getByRole('region', { name: 'Missing Number Chains' })).toBeInTheDocument();
  });

  it('Number Pyramid keeps its puzzles while the child visits the home screen', async () => {
    render(<App />);
    const blocks = () =>
      within(screen.getByRole('group', { name: 'Number pyramid' }))
        .getAllByText(/^Block, row/)
        .map((label) => label.parentElement?.textContent);

    await goTo('#/pyramid');
    const first = blocks();
    await goTo('#/');
    await goTo('#/pyramid');

    expect(blocks()).toEqual(first);
  });

  it.each([
    ['', 'home'],
    ['#', 'home'],
    ['#/', 'home'],
    ['#/pyramid', 'pyramid'],
    ['#/pyramid/', 'pyramid'],
    ['#/missing-number', 'missing-number'],
    ['#shell-demo', 'shell-demo'],
    ['#/shell-demo', 'shell-demo'],
    ['#/nowhere', 'home'],
    ['#pyramid', 'pyramid'],
  ])('parseRoute(%j) is %s', (hash, route) => {
    expect(parseRoute(hash)).toBe(route);
  });
});
