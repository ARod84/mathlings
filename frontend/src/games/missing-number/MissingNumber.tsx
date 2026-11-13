import { useEffect, useRef } from 'react';
import type { Equation, Level } from '../../api/puzzles';
import type { HouseKey } from '../../design/tokens';
import { GameShell } from '../../shell';
import { LoadingScreen, OptionTiles, ProblemScreen, StartScreen } from '../session/SessionScreens';
import { useOptionKeys } from '../session/useOptionKeys';
import { equationLabel, equationParts, linkedTokenIndex } from './equation';
import styles from './MissingNumber.module.css';
import { DEFAULT_TIMING, useMissingNumberGame, type GameTiming } from './useMissingNumberGame';

export interface MissingNumberProps {
  house?: HouseKey;
  /** Leaves the game; shown as the shell's "Games" button. */
  onExit?: () => void;
  /** How long the pauses between steps last. Tests shorten them. */
  timing?: GameTiming;
}

/** The labels name the number range, not a school grade. */
const LEVELS: { level: Level; label: string }[] = [
  { level: 1, label: 'Up to 20' },
  { level: 2, label: 'Up to 100' },
  { level: 3, label: 'Up to 1000' },
];

const INSTRUCTIONS = {
  'choose-level': 'Ready to find some missing numbers?',
  loading: 'Getting your puzzle ready…',
  playing: 'Find the missing number',
  error: 'Let’s try that again',
} as const;

interface EquationViewProps {
  equation: Equation;
  /** What is in the box, if anything. */
  boxValue: number | null;
  /** True once the step is solved and the box holds the answer for good. */
  solved: boolean;
  /** Index of the token to highlight as the number just found, or -1. */
  linkedIndex: number;
}

/** One equation drawn from its tokens. Read as a single phrase by screen readers. */
function EquationView({ equation, boxValue, solved, linkedIndex }: EquationViewProps) {
  const { tokens, equalsAt } = equationParts(equation);
  return (
    <span className={styles.equation} aria-hidden="true">
      {tokens.map((token, index) => (
        <span key={index} className={styles.tokenGroup}>
          {index === equalsAt && <span className={styles.symbol}>=</span>}
          {token.kind === 'number' && (
            <span className={styles.number} data-linked={index === linkedIndex || undefined}>
              {token.value}
            </span>
          )}
          {token.kind === 'operator' && (
            <span className={styles.symbol}>{token.symbol === '+' ? '+' : '−'}</span>
          )}
          {token.kind === 'unknown' && (
            <span
              className={styles.box}
              data-testid="answer-box"
              data-state={solved ? 'solved' : boxValue === null ? 'empty' : 'filled'}
            >
              {boxValue}
            </span>
          )}
        </span>
      ))}
    </span>
  );
}

export function MissingNumber({
  house = 'navigators',
  onExit,
  timing = DEFAULT_TIMING,
}: MissingNumberProps) {
  const game = useMissingNumberGame(timing);
  const { state, locked } = game;
  const { phase, puzzle, stepIndex, selected, answers } = state;
  const playing = phase === 'playing' && puzzle !== null;
  const currentStep = playing ? puzzle.steps[stepIndex] : undefined;

  // After a correct answer the next step slides in, and focus goes with it.
  const currentRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (playing && stepIndex > 0) currentRef.current?.focus();
  }, [playing, stepIndex]);

  // Keys 1-4 pick an option and Enter checks, wherever the focus is in the game.
  useOptionKeys(currentStep?.options, locked, game.select, game.check);

  return (
    <GameShell
      title="Missing Number Chains"
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
          choicesLabel="Or choose a range"
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
          <ol className={styles.chain} aria-label="Steps">
            {puzzle.steps.slice(0, stepIndex + 1).map((step, index) => {
              const current = index === stepIndex;
              // The step just solved keeps its answer in the box while "correct" shows.
              const solvedAnswer = answers[index];
              const solved = solvedAnswer !== undefined;
              const boxValue = solved ? solvedAnswer : current ? selected : null;
              return (
                <li
                  key={`${puzzle.puzzle_id}-${index}`}
                  ref={current ? currentRef : undefined}
                  className={styles.step}
                  data-state={current ? 'current' : 'solved'}
                  role="listitem"
                  tabIndex={current ? -1 : undefined}
                  aria-current={current ? 'step' : undefined}
                  aria-label={equationLabel(step.equation, boxValue, solved)}
                >
                  <EquationView
                    equation={step.equation}
                    boxValue={boxValue}
                    solved={solved}
                    linkedIndex={current ? linkedTokenIndex(step.equation, step.linked_token) : -1}
                  />
                </li>
              );
            })}
          </ol>

          <OptionTiles
            options={currentStep.options}
            selected={selected}
            locked={locked}
            onSelect={game.select}
          />
        </div>
      )}
    </GameShell>
  );
}
