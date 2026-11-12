import { Check, Lightbulb, RotateCcw } from 'lucide-react';
import styles from './ActionBar.module.css';

interface ActionBarProps {
  onHint?: () => void;
  onCheck?: () => void;
  onReset?: () => void;
  /** Draws attention to the Hint button after a wrong answer. */
  nudgeHint?: boolean;
  hidden?: boolean;
}

/**
 * Hint, Check and Reset. All three are always rendered, in the same order and
 * place, so the bar never moves between games. A button without a handler is
 * disabled, not removed.
 */
export function ActionBar({ onHint, onCheck, onReset, nudgeHint = false, hidden }: ActionBarProps) {
  return (
    <div className={styles.bar} role="group" aria-label="Game actions" hidden={hidden}>
      <button
        type="button"
        className={`${styles.button} ${styles.hint}`}
        onClick={onHint}
        disabled={!onHint}
        data-nudge={nudgeHint && onHint ? 'true' : undefined}
      >
        <Lightbulb aria-hidden="true" size={22} strokeWidth={2.4} />
        <span>Hint</span>
      </button>
      <button
        type="button"
        className={`${styles.button} ${styles.check}`}
        onClick={onCheck}
        disabled={!onCheck}
      >
        <Check aria-hidden="true" size={22} strokeWidth={3} />
        <span>Check</span>
      </button>
      <button
        type="button"
        className={`${styles.button} ${styles.reset}`}
        onClick={onReset}
        disabled={!onReset}
      >
        <RotateCcw aria-hidden="true" size={22} strokeWidth={2.4} />
        <span>Reset</span>
      </button>
    </div>
  );
}
