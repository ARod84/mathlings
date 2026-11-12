import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { NumberPyramid } from './NumberPyramid';
import { at, fillOrder, generateRound, type Puzzle } from './pyramid';

const SEED = 7;
const round = generateRound(SEED);
const firstPuzzle = at(round, 0);

const shell = () => screen.getByRole('region', { name: 'Number Pyramid' });
const tray = () => within(screen.getByRole('group', { name: 'Number tiles' }));
const emptyBlocks = () => screen.queryAllByRole('button', { name: /^Empty block/ });
/** The missing numbers, in the order the game offers the empty blocks. */
const missing = (puzzle: Puzzle) =>
  fillOrder(puzzle.rows)
    .filter((cell) => !puzzle.given[cell])
    .map((cell) => at(puzzle.solution, cell));

type User = ReturnType<typeof userEvent.setup>;

const place = async (user: User, value: number) =>
  user.click(at(tray().getAllByRole('button', { name: `Place ${value}` }), 0));

/** Placing the missing numbers in fill order solves the puzzle. */
const solve = async (user: User, puzzle: Puzzle) => {
  for (const value of missing(puzzle)) await place(user, value);
  await user.click(screen.getByRole('button', { name: 'Check' }));
};

describe('NumberPyramid', () => {
  it('solves the first puzzle and moves on to the second', async () => {
    const user = userEvent.setup();
    render(<NumberPyramid seed={SEED} />);

    expect(emptyBlocks()).toHaveLength(missing(firstPuzzle).length);
    // The first block offered is in the lowest row that has a gap, not the top.
    expect(screen.getAllByRole('button', { pressed: true, name: /^Empty block/ })).toHaveLength(1);
    expect(at(emptyBlocks(), 0)).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Check' })).toBeDisabled();

    await solve(user, firstPuzzle);
    expect(shell()).toHaveAttribute('data-feedback', 'correct');

    const solved = await screen.findByTestId('solved-screen', {}, { timeout: 3000 });
    await user.click(within(solved).getByRole('button', { name: /next/i }));

    expect(shell()).toHaveAttribute('data-feedback', 'idle');
    expect(screen.getByText('2 / 8')).toBeInTheDocument();
    expect(emptyBlocks()).toHaveLength(missing(at(round, 1)).length);
  });

  it('gives gentle feedback on a wrong answer and lets the child fix it', async () => {
    const user = userEvent.setup();
    render(<NumberPyramid seed={SEED} />);
    const puzzle = firstPuzzle;
    const [first, ...rest] = missing(puzzle);
    if (first === undefined) throw new Error('expected an empty block');
    const extra = puzzle.tiles.find((value) => !missing(puzzle).includes(value));
    if (extra === undefined) throw new Error('expected an extra tile');

    await place(user, extra);
    for (const value of rest) await place(user, value);
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(shell()).toHaveAttribute('data-feedback', 'incorrect');

    await user.click(screen.getByRole('button', { name: 'Hint' }));
    expect(screen.getByText(/^Take another look/)).toBeInTheDocument();

    // Take the wrong tile out: it returns to the tray and its block is selected again.
    await user.click(screen.getByRole('button', { name: new RegExp(`^Block with ${extra},`) }));
    expect(shell()).toHaveAttribute('data-feedback', 'idle');
    expect(emptyBlocks()).toHaveLength(1);
    expect(at(emptyBlocks(), 0)).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText(/^Take another look/)).not.toBeInTheDocument();

    await place(user, first);
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(shell()).toHaveAttribute('data-feedback', 'correct');
  });

  it('uses each tile once and clears the board on Reset', async () => {
    const user = userEvent.setup();
    render(<NumberPyramid seed={SEED} />);
    const value = at(firstPuzzle.tiles, 0);
    const copies = firstPuzzle.tiles.filter((tile) => tile === value).length;

    await place(user, value);
    expect(tray().queryAllByRole('button', { name: `Place ${value}` })).toHaveLength(copies - 1);
    expect(tray().getByRole('button', { name: `${value}, already placed` })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(emptyBlocks()).toHaveLength(missing(firstPuzzle).length);
    expect(tray().getAllByRole('button', { name: `Place ${value}` })).toHaveLength(copies);
  });

  it('starts a new round after the last puzzle', async () => {
    const user = userEvent.setup();
    render(<NumberPyramid seed={SEED} />);

    for (const puzzle of round) {
      await solve(user, puzzle);
      const solved = await screen.findByTestId('solved-screen', {}, { timeout: 3000 });
      await user.click(within(solved).getByRole('button', { name: /next/i }));
    }

    expect(screen.getByText('1 / 8')).toBeInTheDocument();
    expect(emptyBlocks()).toHaveLength(missing(at(generateRound(SEED + 1), 0)).length);
  }, 30000);
});
