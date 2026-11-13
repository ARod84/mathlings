import { Play, RotateCcw } from 'lucide-react';
import { useId } from 'react';
import styles from './SessionScreens.module.css';

/*
 * The screens and controls every server-checked game shows around its own
 * puzzle: the start screen, the loading placeholder, the friendly error, and
 * the four answer tiles (their keys are in useOptionKeys.ts). They go with
 * usePuzzleSession, which holds the state; these only draw it.
 */

export interface StartChoice {
  key: string | number;
  label: string;
  onChoose: () => void;
}

export interface StartScreenProps {
  /** Starts a round the backend steers. */
  onPlay: () => void;
  /** Heading of the smaller row, for example "Or choose a level". */
  choicesLabel: string;
  choices: readonly StartChoice[];
}

/** One big Play button, then a smaller row of ways to pick for yourself. */
export function StartScreen({ onPlay, choicesLabel, choices }: StartScreenProps) {
  const labelId = useId();
  return (
    <div className={styles.start}>
      {/* The main way in: the backend picks what to play. */}
      <button type="button" className={styles.play} onClick={onPlay}>
        <Play aria-hidden="true" size={26} strokeWidth={3} fill="currentColor" />
        <span>Play</span>
      </button>
      <p className={styles.choicesLabel} id={labelId}>
        {choicesLabel}
      </p>
      <div className={styles.choices} role="group" aria-labelledby={labelId}>
        {choices.map(({ key, label, onChoose }) => (
          <button key={key} type="button" className={styles.choice} onClick={onChoose}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Three blocks taking turns, never a blank screen. */
export function LoadingScreen() {
  return (
    <div className={styles.loading} aria-busy="true">
      <span className={styles.loadingBlocks} aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className={styles.srOnly}>Loading your puzzle</span>
    </div>
  );
}

/** What the child sees when a call fails. `onRetry` repeats whatever failed. */
export function ProblemScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.problem}>
      <p className={styles.problemText}>
        We couldn&rsquo;t get your puzzle just now. Check your connection and try again.
      </p>
      <button type="button" className={styles.tryAgain} onClick={onRetry}>
        <RotateCcw aria-hidden="true" size={20} strokeWidth={3} />
        <span>Try again</span>
      </button>
    </div>
  );
}

export interface OptionTilesProps {
  options: readonly number[];
  /** The option picked for the current step, if any. */
  selected: number | null;
  /** No answer can be changed right now. */
  locked: boolean;
  onSelect: (value: number) => void;
  /** How a number is written on a tile. The plain number unless given. */
  format?: (value: number) => string;
  /** How a screen reader should say it, when the written form would be read wrongly. */
  speak?: (value: number) => string | undefined;
}

/** The answer choices: large tiles, one per option. Keys are in useOptionKeys. */
export function OptionTiles({
  options,
  selected,
  locked,
  onSelect,
  format = String,
  speak,
}: OptionTilesProps) {
  return (
    <div className={styles.options} role="group" aria-label="Answer choices" data-options>
      {options.map((option, index) => (
        <button
          key={option}
          type="button"
          className={styles.option}
          aria-label={speak?.(option)}
          aria-pressed={selected === option}
          aria-keyshortcuts={String(index + 1)}
          disabled={locked}
          onClick={() => onSelect(option)}
        >
          {format(option)}
        </button>
      ))}
    </div>
  );
}
