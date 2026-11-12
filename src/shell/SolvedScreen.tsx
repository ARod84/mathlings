import { ArrowRight } from 'lucide-react';
import { useEffect, useRef, type CSSProperties } from 'react';
import { OrbiPlaceholder } from './orbi/OrbiPlaceholder';
import styles from './SolvedScreen.module.css';

interface SolvedScreenProps {
  onNext?: () => void;
}

const SPARK_COUNT = 10;

/** The completion screen every game shows when a puzzle is solved. */
export function SolvedScreen({ onNext }: SolvedScreenProps) {
  const nextRef = useRef<HTMLButtonElement>(null);

  // The action bar is gone at this point, so hand keyboard focus to "Next".
  useEffect(() => {
    nextRef.current?.focus();
  }, []);

  return (
    <div className={styles.solved} data-testid="solved-screen">
      <div className={styles.celebration} aria-hidden="true">
        {Array.from({ length: SPARK_COUNT }, (_, index) => (
          <span
            key={index}
            className={styles.spark}
            style={{ '--spark-index': index } as CSSProperties}
          />
        ))}
        <OrbiPlaceholder className={styles.orbi} size={92} />
      </div>
      <h2 className={styles.title}>You did it!</h2>
      <p className={styles.message}>Puzzle solved. Great thinking!</p>
      {onNext && (
        <button ref={nextRef} type="button" className={styles.next} onClick={onNext}>
          <span>Next</span>
          <ArrowRight aria-hidden="true" size={24} strokeWidth={3} />
        </button>
      )}
    </div>
  );
}
