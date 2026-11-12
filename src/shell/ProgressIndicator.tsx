import styles from './ProgressIndicator.module.css';
import type { GameProgress } from './types';

/** Above this many puzzles, separate segments get too small, so a single bar is used. */
const MAX_SEGMENTS = 12;

export function ProgressIndicator({ current, total }: GameProgress) {
  const safeTotal = Math.max(1, Math.floor(total));
  const safeCurrent = Math.min(Math.max(0, Math.floor(current)), safeTotal);
  const segmented = safeTotal <= MAX_SEGMENTS;

  return (
    <div
      className={styles.progress}
      role="progressbar"
      aria-label="Progress"
      aria-valuemin={0}
      aria-valuemax={safeTotal}
      aria-valuenow={safeCurrent}
      aria-valuetext={`Puzzle ${safeCurrent} of ${safeTotal}`}
    >
      {segmented ? (
        <span className={styles.segments} aria-hidden="true">
          {Array.from({ length: safeTotal }, (_, index) => (
            <span
              key={index}
              className={styles.segment}
              data-filled={index < safeCurrent ? 'true' : undefined}
            />
          ))}
        </span>
      ) : (
        <span className={styles.bar} aria-hidden="true">
          <span
            className={styles.barFill}
            style={{ width: `${(safeCurrent / safeTotal) * 100}%` }}
          />
        </span>
      )}
      <span className={styles.count} aria-hidden="true">
        {safeCurrent} / {safeTotal}
      </span>
    </div>
  );
}
