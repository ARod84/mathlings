import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { HOUSE_KEYS } from '../design/tokens';
import { GameShell } from './GameShell';
import type { GameShellProps } from './types';

function renderShell(overrides: Partial<GameShellProps> = {}) {
  const props: GameShellProps = {
    title: 'Make Ten',
    instruction: 'Tap the number that makes 10 with 7',
    house: 'navigators',
    progress: { current: 3, total: 8 },
    feedback: 'idle',
    children: <button type="button">3</button>,
    ...overrides,
  };
  const view = render(<GameShell {...props} />);
  const rerenderShell = (next: Partial<GameShellProps>) =>
    view.rerender(<GameShell {...props} {...next} />);
  return { ...view, rerenderShell };
}

const shell = () => screen.getByRole('region', { name: 'Make Ten' });
const liveRegion = () => screen.getByRole('status');

describe('GameShell layout', () => {
  it('renders the title and the instruction as a heading', () => {
    renderShell();
    expect(screen.getByText('Make Ten')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Tap the number that makes 10 with 7' }),
    ).toBeInTheDocument();
  });

  it('shows only one instruction at a time', () => {
    const { rerenderShell } = renderShell();
    rerenderShell({ instruction: 'Now make 10 with 6' });
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Now make 10 with 6' })).toBeInTheDocument();
  });

  it('renders the play area children', () => {
    renderShell();
    expect(
      within(screen.getByTestId('play-area')).getByRole('button', { name: '3' }),
    ).toBeVisible();
  });

  it('shows progress as text and as an accessible progress bar', () => {
    renderShell();
    expect(screen.getByText('3 / 8')).toBeInTheDocument();
    const progress = screen.getByRole('progressbar', { name: 'Progress' });
    expect(progress).toHaveAttribute('aria-valuenow', '3');
    expect(progress).toHaveAttribute('aria-valuemax', '8');
    expect(progress).toHaveAttribute('aria-valuetext', 'Puzzle 3 of 8');
  });

  it.each(HOUSE_KEYS)('applies the %s house to the whole shell', (house) => {
    renderShell({ house });
    expect(shell()).toHaveAttribute('data-house', house);
  });

  it('always renders Hint, Check and Reset in that order, each with a text label', () => {
    renderShell();
    const actions = screen.getByRole('group', { name: 'Game actions' });
    const labels = within(actions)
      .getAllByRole('button')
      .map((button) => button.textContent);
    expect(labels).toEqual(['Hint', 'Check', 'Reset']);
  });

  it('disables an action that has no handler, keeping it in place', () => {
    renderShell({ onCheck: vi.fn() });
    expect(screen.getByRole('button', { name: 'Hint' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Check' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();
  });
});

describe('GameShell actions', () => {
  it('calls the matching handler for Hint, Check and Reset', async () => {
    const user = userEvent.setup();
    const onHint = vi.fn();
    const onCheck = vi.fn();
    const onReset = vi.fn();
    renderShell({ onHint, onCheck, onReset });

    await user.click(screen.getByRole('button', { name: 'Hint' }));
    expect(onHint).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(onCheck).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('works from the keyboard', async () => {
    const user = userEvent.setup();
    const onCheck = vi.fn();
    renderShell({ onHint: vi.fn(), onCheck, onReset: vi.fn() });

    screen.getByRole('button', { name: 'Hint' }).focus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Check' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onCheck).toHaveBeenCalledTimes(1);
  });

  it('calls onNext from the solved screen', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    renderShell({ feedback: 'solved', onNext });
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});

describe('GameShell feedback states', () => {
  it('idle: no message, no completion screen, no nudge', () => {
    renderShell({ onHint: vi.fn() });
    expect(shell()).toHaveAttribute('data-feedback', 'idle');
    expect(liveRegion()).toBeEmptyDOMElement();
    expect(screen.queryByTestId('solved-screen')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hint' })).not.toHaveAttribute('data-nudge');
  });

  it('correct: marks the shell and shows a positive message', () => {
    renderShell({ feedback: 'correct' });
    expect(shell()).toHaveAttribute('data-feedback', 'correct');
    expect(liveRegion()).toHaveTextContent('That’s right!');
    expect(screen.getByTestId('play-area')).toBeVisible();
  });

  it('incorrect: encourages another try and nudges toward the hint', () => {
    renderShell({ feedback: 'incorrect', onHint: vi.fn() });
    expect(shell()).toHaveAttribute('data-feedback', 'incorrect');
    expect(liveRegion()).toHaveTextContent('Not quite. Try again, or tap Hint for a clue.');
    expect(screen.getByRole('button', { name: 'Hint' })).toHaveAttribute('data-nudge', 'true');
  });

  it('incorrect: never uses error wording or an alert role', () => {
    renderShell({ feedback: 'incorrect', onHint: vi.fn() });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(liveRegion().textContent).not.toMatch(/wrong|error|fail/i);
  });

  it('incorrect with a hint already showing: points back to the hint without nudging', () => {
    renderShell({ feedback: 'incorrect', onHint: vi.fn(), hint: 'Count up from 7.' });
    expect(liveRegion()).toHaveTextContent('Take another look at ORBI’s hint.');
    expect(screen.getByRole('button', { name: 'Hint' })).not.toHaveAttribute('data-nudge');
  });

  it('solved: shows the completion screen with Next and hides the puzzle and actions', () => {
    renderShell({ feedback: 'solved', onNext: vi.fn(), onCheck: vi.fn() });
    const solved = screen.getByTestId('solved-screen');
    expect(within(solved).getByRole('heading', { name: 'You did it!' })).toBeVisible();
    expect(within(solved).getByRole('button', { name: 'Next' })).toHaveFocus();
    expect(screen.getByTestId('play-area')).not.toBeVisible();
    expect(screen.queryByRole('button', { name: 'Check' })).not.toBeInTheDocument();
  });

  it('complete: shows the round-complete screen with Play again instead of the solved screen', () => {
    renderShell({
      feedback: 'complete',
      progress: { current: 8, total: 8 },
      onNext: vi.fn(),
      onCheck: vi.fn(),
    });
    const complete = screen.getByTestId('round-complete-screen');
    expect(within(complete).getByRole('heading', { name: 'Round complete!' })).toBeVisible();
    expect(within(complete).getByText('You solved all 8 puzzles. Stellar work!')).toBeVisible();
    expect(within(complete).getByRole('button', { name: 'Play again' })).toHaveFocus();
    expect(screen.queryByTestId('solved-screen')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
    expect(screen.getByTestId('play-area')).not.toBeVisible();
    expect(screen.queryByRole('button', { name: 'Check' })).not.toBeInTheDocument();
    expect(liveRegion()).toHaveTextContent('Round complete! You solved all 8 puzzles.');
  });

  it('complete: Play again calls onNext', async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    renderShell({ feedback: 'complete', onNext });
    await user.click(screen.getByRole('button', { name: 'Play again' }));
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it('solved: keeps the play area mounted so the game keeps its state', () => {
    const { rerenderShell } = renderShell();
    const child = within(screen.getByTestId('play-area')).getByRole('button', { name: '3' });
    rerenderShell({ feedback: 'solved' });
    rerenderShell({ feedback: 'idle' });
    expect(within(screen.getByTestId('play-area')).getByRole('button', { name: '3' })).toBe(child);
  });
});

describe('GameShell hint bubble', () => {
  it('is absent without a hint', () => {
    renderShell({ hint: null });
    expect(screen.queryByText('ORBI’s hint')).not.toBeInTheDocument();
  });

  it('shows the hint next to the ORBI placeholder', () => {
    const { container } = renderShell({ hint: 'Count up from 7.' });
    expect(screen.getByText('ORBI’s hint')).toBeInTheDocument();
    expect(screen.getByText('Count up from 7.')).toBeInTheDocument();
    expect(container.querySelector('[data-placeholder="orbi"]')).toBeInTheDocument();
  });
});

describe('GameShell live region', () => {
  it('is a polite live region that updates as feedback changes', () => {
    const { rerenderShell } = renderShell({ onHint: vi.fn() });
    const region = liveRegion();
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toBeEmptyDOMElement();

    rerenderShell({ feedback: 'incorrect', onHint: vi.fn() });
    expect(region).toHaveTextContent('Not quite. Try again, or tap Hint for a clue.');

    rerenderShell({ feedback: 'correct' });
    expect(region).toHaveTextContent('That’s right!');

    rerenderShell({ feedback: 'solved' });
    expect(region).toHaveTextContent('Puzzle solved!');

    rerenderShell({ feedback: 'idle' });
    expect(region).toBeEmptyDOMElement();
    // Same element throughout: a remounted region would not be announced.
    expect(liveRegion()).toBe(region);
  });
});

describe('GameShell sound toggle', () => {
  it('starts muted and unmutes on the first interaction with the page', async () => {
    const user = userEvent.setup();
    renderShell({ onCheck: vi.fn() });
    const toggle = screen.getByRole('button', { name: 'Sound' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('lets the user turn sound on, then off again, with the toggle', async () => {
    const user = userEvent.setup();
    renderShell();
    const toggle = screen.getByRole('button', { name: 'Sound' });

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('stays muted after the user mutes, whatever they do next', async () => {
    const user = userEvent.setup();
    renderShell({ onCheck: vi.fn() });
    const toggle = screen.getByRole('button', { name: 'Sound' });

    await user.click(screen.getByRole('button', { name: 'Check' }));
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });
});
