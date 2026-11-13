import { ArrowLeft, Check, Sparkles, Volume2, VolumeX } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { ActionBar } from './ActionBar';
import styles from './GameShell.module.css';
import { HintBubble } from './HintBubble';
import { ProgressIndicator } from './ProgressIndicator';
import { SolvedScreen } from './SolvedScreen';
import type { FeedbackState, GameShellProps } from './types';
import { SOUND_TOGGLE_ATTRIBUTE, useFeedbackSound } from './useFeedbackSound';

function feedbackMessage(
  feedback: FeedbackState,
  canHint: boolean,
  hintShown: boolean,
  total: number,
): string {
  switch (feedback) {
    case 'correct':
      return 'That’s right!';
    case 'incorrect':
      if (hintShown) return 'Not quite. Take another look at ORBI’s hint.';
      if (canHint) return 'Not quite. Try again, or tap Hint for a clue.';
      return 'Not quite. Have another go!';
    case 'solved':
      return 'Puzzle solved!';
    case 'complete':
      return `Round complete! You solved all ${total} puzzles.`;
    case 'idle':
      return '';
  }
}

const soundToggleMarker = { [SOUND_TOGGLE_ATTRIBUTE]: '' };

/**
 * The one layout every game renders inside. A game supplies the play area
 * (children) and its own logic; the shell owns the title, progress,
 * instruction, action bar, hint bubble, feedback visuals, sounds and
 * screen-reader announcements.
 */
export function GameShell({
  title,
  instruction,
  house,
  progress,
  feedback,
  hint,
  onHint,
  onCheck,
  onReset,
  onNext,
  onExit,
  children,
}: GameShellProps) {
  const { muted, toggleMuted, play } = useFeedbackSound();

  // Play a tone when the feedback state changes (never on first render).
  const previousFeedback = useRef(feedback);
  useEffect(() => {
    if (previousFeedback.current === feedback) return;
    previousFeedback.current = feedback;
    if (feedback !== 'idle') play(feedback);
  }, [feedback, play]);

  // Either completion screen is up: the play area and the action bar step aside.
  const solved = feedback === 'solved' || feedback === 'complete';
  const hintText = hint?.trim() ? hint : null;
  const message = feedbackMessage(feedback, Boolean(onHint), hintText !== null, progress.total);

  return (
    <section
      className={styles.shell}
      data-house={house}
      data-feedback={feedback}
      aria-label={title}
    >
      <header className={styles.header}>
        {onExit && (
          <button type="button" className={styles.exit} onClick={onExit} aria-label="Back to games">
            <ArrowLeft aria-hidden="true" size={20} strokeWidth={3} />
            <span>Games</span>
          </button>
        )}
        <p className={styles.title}>{title}</p>
        <div className={styles.headerTools}>
          <ProgressIndicator current={progress.current} total={progress.total} />
          <button
            type="button"
            className={styles.soundToggle}
            onClick={toggleMuted}
            aria-pressed={!muted}
            aria-label="Sound"
            title={muted ? 'Sound is off' : 'Sound is on'}
            {...soundToggleMarker}
          >
            {muted ? (
              <VolumeX aria-hidden="true" size={22} />
            ) : (
              <Volume2 aria-hidden="true" size={22} />
            )}
          </button>
        </div>
      </header>

      <div className={styles.body}>
        {/* Kept mounted while solved, so the game keeps its state behind the completion screen. */}
        <div className={styles.stage} hidden={solved}>
          <h1 className={styles.instruction}>{instruction}</h1>
          <div className={styles.playArea} data-testid="play-area">
            {children}
          </div>
        </div>

        {solved && (
          <SolvedScreen
            variant={feedback === 'complete' ? 'round' : 'puzzle'}
            total={progress.total}
            onNext={onNext}
          />
        )}

        {/* Always mounted, so screen readers announce every change. */}
        <div className={styles.feedback} role="status" aria-live="polite">
          {message && (
            <p
              className={solved ? styles.visuallyHidden : styles.feedbackMessage}
              data-tone={feedback}
            >
              {!solved && (
                <span className={styles.feedbackIcon} aria-hidden="true">
                  {feedback === 'correct' ? (
                    <Check size={18} strokeWidth={3.5} />
                  ) : (
                    <Sparkles size={18} strokeWidth={2.6} />
                  )}
                </span>
              )}
              {message}
            </p>
          )}
        </div>

        <div className={styles.hintSlot} aria-live="polite">
          {hintText !== null && !solved && <HintBubble text={hintText} />}
        </div>
      </div>

      <ActionBar
        onHint={onHint}
        onCheck={onCheck}
        onReset={onReset}
        nudgeHint={feedback === 'incorrect' && hintText === null}
        hidden={solved}
      />
    </section>
  );
}
