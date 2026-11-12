import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ShellDemo } from './ShellDemo';

const shell = () => screen.getByRole('region', { name: 'Make Ten' });

describe('ShellDemo', () => {
  it('plays through the dummy puzzle: wrong answer, then the right one', async () => {
    const user = userEvent.setup();
    render(<ShellDemo />);
    expect(screen.getByRole('button', { name: 'Check' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: '2' }));
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(shell()).toHaveAttribute('data-feedback', 'incorrect');

    await user.click(screen.getByRole('button', { name: '3' }));
    expect(shell()).toHaveAttribute('data-feedback', 'idle');
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(shell()).toHaveAttribute('data-feedback', 'correct');
    expect(await screen.findByTestId('solved-screen', {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('switches the house and forces feedback states from the dev toolbar', async () => {
    const user = userEvent.setup();
    render(<ShellDemo />);

    await user.click(screen.getByRole('button', { name: 'cultivators' }));
    expect(shell()).toHaveAttribute('data-house', 'cultivators');

    for (const state of ['correct', 'incorrect', 'solved', 'complete', 'idle'] as const) {
      await user.click(screen.getByRole('button', { name: state }));
      expect(shell()).toHaveAttribute('data-feedback', state);
    }
  });
});
