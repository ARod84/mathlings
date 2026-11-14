import { ArrowRight, RotateCcw } from 'lucide-react';
import { useEffect, useRef, type CSSProperties } from 'react';
import { OrbiPlaceholder } from './orbi/OrbiPlaceholder';
import styles from './SolvedScreen.module.css';
import type { SolvedCopy } from './types';

interface SolvedScreenProps {
  /** 'puzzle': one puzzle solved. 'round': the last puzzle of the round solved. */
  variant?: 'puzzle' | 'round';
  /** Number of puzzles in the round; used by the 'round' variant. */
  total?: number;
  onNext?: () => void;
  /** Other words for the message and the button; the 'puzzle' variant only. */
  copy?: SolvedCopy;
}

const SPARKS = { puzzle: 10, round: 20 } as const;
/** Same limit as the progress indicator: beyond this the blocks get too small. */
const MAX_TROPHY_BLOCKS = 12;

/**
 * The completion screen every game shows: after each puzzle ('puzzle'), and a
 * bigger one when the whole round is done ('round').
 */
export function SolvedScreen({ variant = 'puzzle', total = 0, onNext, copy }: SolvedScreenProps) {
  const nextRef = useRef<HTMLButtonElement>(null);
  const round = variant === 'round';
  const words = round ? undefined : copy;
  const count = Math.max(0, Math.floor(total));

  // The action bar is gone at this point, so hand keyboard focus to the button.
  useEffect(() => {
    nextRef.current?.focus();
  }, []);

  return (
    <div
      className={styles.solved}
      data-variant={variant}
      data-testid={round ? 'round-complete-screen' : 'solved-screen'}
    >
      <div className={styles.celebration} aria-hidden="true">
        {Array.from({ length: SPARKS[variant] }, (_, index) => (
          <span
            key={index}
            className={styles.spark}
            style={{ '--spark-index': index } as CSSProperties}
          />
        ))}
        <OrbiPlaceholder className={styles.orbi} size={round ? 108 : 92} />
      </div>
      <h2 className={styles.title}>{round ? 'Round complete!' : 'You did it!'}</h2>
      {round && count > 0 && count <= MAX_TROPHY_BLOCKS && (
        // One gold block per solved puzzle, popping in one after another.
        <div className={styles.trophies} aria-hidden="true">
          {Array.from({ length: count }, (_, index) => (
            <span
              key={index}
              className={styles.trophy}
              style={{ '--trophy-index': index } as CSSProperties}
            />
          ))}
        </div>
      )}
      <p className={styles.message}>
        {round
          ? count > 0
            ? `You solved all ${count} puzzles. Stellar work!`
            : 'You solved every puzzle. Stellar work!'
          : (words?.message ?? 'Puzzle solved. Great thinking!')}
      </p>
      {onNext && (
        <button ref={nextRef} type="button" className={styles.next} onClick={onNext}>
          {round && <RotateCcw aria-hidden="true" size={22} strokeWidth={3} />}
          <span>{round ? 'Play again' : (words?.nextLabel ?? 'Next')}</span>
          {!round && <ArrowRight aria-hidden="true" size={24} strokeWidth={3} />}
        </button>
      )}
    </div>
  );
}
