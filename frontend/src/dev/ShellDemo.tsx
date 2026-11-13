import { useEffect, useState } from 'react';
import { HOUSE_KEYS, type HouseKey } from '../design/tokens';
import { GameShell, type FeedbackState } from '../shell';
import styles from './ShellDemo.module.css';

/*
 * Dev-only review page for the GameShell. Not a real game: one hard-coded
 * puzzle, plus a toolbar that switches the house and forces each feedback
 * state so every visual state can be checked in all five house colors.
 */

const OPTIONS = [2, 3, 4] as const;
const ANSWER = 3;
const HINT = 'Start at 7 and count up to 10: 8… 9… 10. How many jumps was that?';
const FEEDBACK_STATES: FeedbackState[] = ['idle', 'correct', 'incorrect', 'solved', 'complete'];

export function ShellDemo() {
  const [house, setHouse] = useState<HouseKey>('navigators');
  const [selected, setSelected] = useState<number | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [gameFeedback, setGameFeedback] = useState<FeedbackState>('idle');
  // null means "follow the puzzle"; otherwise the toolbar is forcing a state.
  const [forced, setForced] = useState<FeedbackState | null>(null);

  const feedback = forced ?? gameFeedback;

  // A real game would do the same: show "correct" briefly, then finish.
  useEffect(() => {
    if (gameFeedback !== 'correct') return;
    const timer = window.setTimeout(() => setGameFeedback('solved'), 1100);
    return () => window.clearTimeout(timer);
  }, [gameFeedback]);

  const reset = () => {
    setSelected(null);
    setHint(null);
    setGameFeedback('idle');
    setForced(null);
  };

  const choose = (option: number) => {
    setSelected(option);
    setGameFeedback('idle');
    setForced(null);
  };

  const check = () => {
    setForced(null);
    setGameFeedback(selected === ANSWER ? 'correct' : 'incorrect');
  };

  return (
    <main className={styles.page}>
      <aside className={styles.toolbar} aria-label="Dev toolbar">
        <span className={styles.badge}>Dev toolbar</span>
        <div className={styles.group} role="group" aria-label="House">
          <span className={styles.groupLabel}>House</span>
          {HOUSE_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={styles.chip}
              data-house={key}
              aria-pressed={house === key}
              onClick={() => setHouse(key)}
            >
              <span className={styles.swatch} aria-hidden="true" />
              {key}
            </button>
          ))}
        </div>
        <div className={styles.group} role="group" aria-label="Feedback state">
          <span className={styles.groupLabel}>Feedback</span>
          <button
            type="button"
            className={styles.chip}
            aria-pressed={forced === null}
            onClick={() => setForced(null)}
          >
            live
          </button>
          {FEEDBACK_STATES.map((state) => (
            <button
              key={state}
              type="button"
              className={styles.chip}
              aria-pressed={forced === state}
              onClick={() => setForced(state)}
            >
              {state}
            </button>
          ))}
        </div>
      </aside>

      <GameShell
        title="Make Ten"
        instruction="Tap the number that makes 10 with 7"
        house={house}
        progress={{ current: 3, total: 8 }}
        feedback={feedback}
        hint={hint}
        onHint={() => setHint(HINT)}
        onCheck={selected === null ? undefined : check}
        onReset={reset}
        onNext={reset}
      >
        <div className={styles.puzzle}>
          <p className={styles.sum} aria-hidden="true">
            7 + <span className={styles.blank}>{selected ?? '?'}</span> = 10
          </p>
          <div className={styles.options} role="group" aria-label="Answer choices">
            {OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={styles.option}
                aria-pressed={selected === option}
                onClick={() => choose(option)}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      </GameShell>
    </main>
  );
}
