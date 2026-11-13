import { useEffect } from 'react';

/**
 * Keys 1 to 4 pick an option and Enter checks, wherever the focus is in the
 * game. `options` is undefined when there is nothing to answer.
 */
export function useOptionKeys(
  options: readonly number[] | undefined,
  locked: boolean,
  select: (value: number) => void,
  check: () => void,
): void {
  useEffect(() => {
    if (!options || locked) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const picked = options[Number(event.key) - 1];
      if (/^[1-9]$/.test(event.key) && picked !== undefined) {
        select(picked);
        return;
      }
      if (event.key !== 'Enter') return;
      // Enter on one of the shell's own buttons (Hint, Reset, sound...) is that button's.
      const target = event.target instanceof Element ? event.target.closest('button, a') : null;
      if (target && !target.closest('[data-options]')) return;
      event.preventDefault();
      check();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [options, locked, select, check]);
}
