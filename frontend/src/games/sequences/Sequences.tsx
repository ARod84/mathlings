import { useEffect, useRef, type CSSProperties } from 'react';
import type { Level } from '../../api/puzzles';
import type { HouseKey } from '../../design/tokens';
import { GameShell } from '../../shell';
import { LoadingScreen, OptionTiles, ProblemScreen, StartScreen } from '../session/SessionScreens';
import { useOptionKeys } from '../session/useOptionKeys';
import { formatJump, formatNumber, rowLabel, spokenNumber, visibleJumps } from './sequence';
import styles from './Sequences.module.css';
import { DEFAULT_TIMING, useSequencesGame, type GameTiming } from './useSequencesGame';

export interface SequencesProps {
  house?: HouseKey;
  /** Leaves the game; shown as the shell's "Games" button. */
  onExit?: () => void;
  /** How long the pauses between steps last. Tests shorten them. */
  timing?: GameTiming;
}

const LEVELS: { level: Level; label: string }[] = [
  { level: 1, label: 'Counting on' },
  { level: 2, label: 'Skip counting' },
  { level: 3, label: 'Tricky patterns' },
];

const INSTRUCTIONS = {
  'choose-level': 'Ready to spot some patterns?',
  loading: 'Getting your puzzle ready…',
  playing: 'Which number is missing?',
  error: 'Let’s try that again',
} as const;

/** The second hint tier names the rule; from then on the jumps are drawn too. */
const JUMPS_FROM_HINT_TIER = 2;

interface JumpArcsProps {
  terms: readonly (number | null)[];
}

/**
 * Small arcs between neighbouring numbers, each labelled with the jump: "+4".
 * Decoration for a hint the child has already read, so hidden from screen
 * readers. Only between two numbers the puzzle shows: see visibleJumps.
 */
function JumpArcs({ terms }: JumpArcsProps) {
  return (
    <div className={styles.arcs} aria-hidden="true" data-testid="jump-arcs">
      {visibleJumps(terms).map(({ from, difference }) => (
        <span
          key={from}
          className={styles.arc}
          data-from={from}
          // In the column of the block it starts from; the stylesheet stretches
          // it from the middle of that block to the middle of the next.
          style={{ gridColumn: from + 1 }}
        >
          <span className={styles.arcLabel}>{formatJump(difference)}</span>
          <svg className={styles.arcCurve} viewBox="0 0 100 40" preserveAspectRatio="none">
            <path d="M 4 38 Q 50 -22 96 38" />
          </svg>
        </span>
      ))}
    </div>
  );
}

export function Sequences({
  house = 'scientists',
  onExit,
  timing = DEFAULT_TIMING,
}: SequencesProps) {
  const game = useSequencesGame(timing);
  const { state, locked } = game;
  const { phase, puzzle, stepIndex, selected, answers } = state;
  const playing = phase === 'playing' && puzzle !== null;
  const currentStep = playing ? puzzle.steps[stepIndex] : undefined;

  // After a correct answer the next blank becomes the current one, and focus goes with it.
  const currentRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (playing && stepIndex > 0) currentRef.current?.focus();
  }, [playing, stepIndex]);

  // Keys 1-4 pick an option and Enter checks, wherever the focus is in the game.
  useOptionKeys(currentStep?.options, locked, game.select, game.check);

  // Blanks the child has solved, by their place in the row.
  const solved = new Map<number, number>();
  if (playing) {
    answers.forEach((answer, index) => {
      const step = puzzle.steps[index];
      if (step) solved.set(step.position, answer);
    });
  }
  const showJumps = playing && state.hintTier >= JUMPS_FROM_HINT_TIER;
  // The longest number a block may have to hold: the terms on show, and every
  // option, since a blank ends up holding one of them. The stylesheet sizes
  // the numbers from it, so short numbers are not shrunk for nothing.
  const longest = playing
    ? Math.max(
        ...puzzle.terms.map((term) => (term === null ? 0 : formatNumber(term).length)),
        ...puzzle.steps.flatMap((step) => step.options.map((o) => formatNumber(o).length)),
      )
    : 0;

  return (
    <GameShell
      title="Next in Line"
      instruction={INSTRUCTIONS[phase]}
      house={house}
      progress={{
        current: phase === 'choose-level' ? 0 : state.puzzleIndex + 1,
        total: game.roundSize,
      }}
      feedback={playing ? state.feedback : 'idle'}
      hint={playing ? state.hint : null}
      onHint={playing && game.canHint ? game.requestHint : undefined}
      onCheck={playing && !locked && selected !== null ? game.check : undefined}
      onReset={playing && !locked && selected !== null ? game.reset : undefined}
      onNext={game.next}
      onExit={onExit}
    >
      {phase === 'choose-level' && (
        <StartScreen
          onPlay={game.play}
          choicesLabel="Or choose a level"
          choices={LEVELS.map(({ level, label }) => ({
            key: level,
            label,
            onChoose: () => game.chooseLevel(level),
          }))}
        />
      )}

      {phase === 'loading' && <LoadingScreen />}

      {phase === 'error' && <ProblemScreen onRetry={game.retry} />}

      {playing && currentStep && (
        <div className={styles.game}>
          <div
            className={styles.rowArea}
            style={{ '--count': puzzle.terms.length, '--chars': longest } as CSSProperties}
          >
            {/* The space is kept whether or not the arcs are drawn, so the row does not jump. */}
            <div className={styles.arcsSpace}>{showJumps && <JumpArcs terms={puzzle.terms} />}</div>
            <ol
              className={styles.row}
              role="list"
              aria-label={rowLabel(puzzle.terms, solved)}
              data-testid="sequence-row"
            >
              {puzzle.terms.map((term, position) => {
                const key = `${puzzle.puzzle_id}-${position}`;
                if (term !== null) {
                  return (
                    <li
                      key={key}
                      className={styles.block}
                      data-state="given"
                      aria-label={term < 0 ? spokenNumber(term) : undefined}
                    >
                      {formatNumber(term)}
                    </li>
                  );
                }
                const blankIndex = puzzle.steps.findIndex((step) => step.position === position);
                const solvedValue = solved.get(position);
                if (solvedValue !== undefined) {
                  // Filled in for good: the child got it right.
                  return (
                    <li
                      key={key}
                      className={styles.block}
                      data-state="solved"
                      aria-label={spokenNumber(solvedValue)}
                    >
                      {formatNumber(solvedValue)}
                    </li>
                  );
                }
                if (blankIndex !== stepIndex) {
                  return (
                    <li key={key} className={styles.block} data-state="blank" aria-label="blank" />
                  );
                }
                const place = `Blank ${stepIndex + 1} of ${puzzle.steps.length}`;
                return (
                  <li
                    key={key}
                    ref={currentRef}
                    className={styles.block}
                    data-state="current"
                    data-filled={selected !== null || undefined}
                    tabIndex={-1}
                    aria-current="step"
                    aria-label={
                      selected === null ? place : `${place}, with ${spokenNumber(selected)}`
                    }
                  >
                    {selected !== null && formatNumber(selected)}
                  </li>
                );
              })}
            </ol>
          </div>

          <OptionTiles
            options={currentStep.options}
            selected={selected}
            locked={locked}
            onSelect={game.select}
            format={formatNumber}
            speak={(value) => (value < 0 ? spokenNumber(value) : undefined)}
          />
        </div>
      )}
    </GameShell>
  );
}
