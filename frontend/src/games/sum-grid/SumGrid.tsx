import { useEffect, useId, useRef, type CSSProperties } from 'react';
import type { Level } from '../../api/puzzles';
import type { HouseKey } from '../../design/tokens';
import { GameShell } from '../../shell';
import { LoadingScreen, OptionTiles, ProblemScreen, StartScreen } from '../session/SessionScreens';
import { useOptionKeys } from '../session/useOptionKeys';
import { blankLabel, cellKey, gridDescription, onLine, type Solved } from './grid';
import styles from './SumGrid.module.css';
import { DEFAULT_TIMING, useSumGridGame, type GameTiming } from './useSumGridGame';

export interface SumGridProps {
  house?: HouseKey;
  /** Leaves the game; shown as the shell's "Games" button. */
  onExit?: () => void;
  /** How long the pauses between steps last. Tests shorten them. */
  timing?: GameTiming;
}

const LEVELS: { level: Level; label: string }[] = [
  { level: 1, label: '2 by 2' },
  { level: 2, label: '3 by 3' },
  { level: 3, label: 'Big numbers' },
];

const INSTRUCTIONS = {
  'choose-level': 'Ready to make the sums add up?',
  loading: 'Getting your puzzle ready…',
  playing: 'Which number goes in the box?',
  error: 'Let’s try that again',
} as const;

/**
 * The first hint tier says which line to look at; from then on that line is
 * drawn highlighted too. Not before: spotting the line is part of the puzzle.
 */
const HIGHLIGHT_FROM_HINT_TIER = 1;

export function SumGrid({ house = 'artisans', onExit, timing = DEFAULT_TIMING }: SumGridProps) {
  const game = useSumGridGame(timing);
  const { state, locked } = game;
  const { phase, puzzle, stepIndex, selected, answers } = state;
  const playing = phase === 'playing' && puzzle !== null;
  const currentStep = playing ? puzzle.steps[stepIndex] : undefined;
  const descriptionId = useId();

  // After a correct answer the next blank becomes the current one, and focus goes with it.
  const currentRef = useRef<HTMLTableCellElement>(null);
  useEffect(() => {
    if (playing && stepIndex > 0) currentRef.current?.focus();
  }, [playing, stepIndex]);

  // Keys 1-4 pick an option and Enter checks, wherever the focus is in the game.
  useOptionKeys(currentStep?.options, locked, game.select, game.check);

  // Blanks the child has solved, by their place in the grid.
  const solved: Solved = new Map(
    playing
      ? answers.flatMap((answer, index) => {
          const step = puzzle.steps[index];
          return step ? [[cellKey(step.cell.row, step.cell.col), answer] as const] : [];
        })
      : [],
  );
  const highlighted =
    playing && currentStep && state.hintTier >= HIGHLIGHT_FROM_HINT_TIER ? currentStep.line : null;
  // The longest number a block may have to hold: cells, targets and every
  // option, since a blank ends up holding one of them.
  const longest = playing
    ? Math.max(
        ...puzzle.cells.flat().map((value) => (value === null ? 0 : String(value).length)),
        ...[...puzzle.row_targets, ...puzzle.col_targets].map((value) => String(value).length),
        ...puzzle.steps.flatMap((step) => step.options.map((option) => String(option).length)),
      )
    : 0;

  return (
    <GameShell
      title="Sum Grid"
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
            className={styles.gridArea}
            style={{ '--count': puzzle.size + 1, '--chars': longest } as CSSProperties}
          >
            {/*
             * A real table: the grid is rows and columns with a total at the
             * end of each, which is what a table is. Screen readers read it
             * cell by cell, and the description below reads it line by line.
             */}
            <table
              className={styles.grid}
              aria-label={`Sum grid, ${puzzle.size} by ${puzzle.size}`}
              aria-describedby={descriptionId}
              data-testid="sum-grid"
            >
              <tbody>
                {puzzle.cells.map((row, r) => (
                  <tr key={`${puzzle.puzzle_id}-${r}`}>
                    {row.map((value, c) => {
                      const cell = { row: r, col: c };
                      const lit = highlighted !== null && onLine(highlighted, cell);
                      const key = `${puzzle.puzzle_id}-${r}-${c}`;
                      if (value !== null) {
                        return (
                          <td key={key} className={styles.cell} data-highlighted={lit || undefined}>
                            <span className={styles.block} data-state="given">
                              {value}
                            </span>
                          </td>
                        );
                      }
                      const found = solved.get(cellKey(r, c));
                      if (found !== undefined) {
                        return (
                          <td key={key} className={styles.cell} data-highlighted={lit || undefined}>
                            <span className={styles.block} data-state="solved">
                              {found}
                            </span>
                          </td>
                        );
                      }
                      const isCurrent = currentStep.cell.row === r && currentStep.cell.col === c;
                      if (!isCurrent) {
                        return (
                          <td
                            key={key}
                            className={styles.cell}
                            aria-label="blank"
                            data-highlighted={lit || undefined}
                          >
                            <span className={styles.block} data-state="blank" />
                          </td>
                        );
                      }
                      return (
                        <td
                          key={key}
                          ref={currentRef}
                          className={styles.cell}
                          tabIndex={-1}
                          aria-current="step"
                          aria-label={blankLabel(cell, stepIndex, puzzle.steps.length, selected)}
                          data-highlighted={lit || undefined}
                        >
                          <span
                            className={styles.block}
                            data-state="current"
                            data-filled={selected !== null || undefined}
                          >
                            {selected}
                          </span>
                        </td>
                      );
                    })}
                    <td
                      className={styles.cell}
                      aria-label={`Target ${puzzle.row_targets[r]}`}
                      data-highlighted={
                        (highlighted?.kind === 'row' && highlighted.index === r) || undefined
                      }
                    >
                      <span className={styles.block} data-kind="target">
                        {puzzle.row_targets[r]}
                      </span>
                    </td>
                  </tr>
                ))}
                <tr>
                  {puzzle.col_targets.map((target, c) => (
                    <td
                      key={`${puzzle.puzzle_id}-target-${c}`}
                      className={styles.cell}
                      aria-label={`Target ${target}`}
                      data-highlighted={
                        (highlighted?.kind === 'col' && highlighted.index === c) || undefined
                      }
                    >
                      <span className={styles.block} data-kind="target">
                        {target}
                      </span>
                    </td>
                  ))}
                  {/* The corner under the row targets holds nothing. */}
                  <td className={styles.cell} aria-hidden="true" />
                </tr>
              </tbody>
            </table>
            <p id={descriptionId} className={styles.srOnly}>
              {gridDescription(puzzle.cells, puzzle.row_targets, puzzle.col_targets, solved)}
            </p>
          </div>

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
