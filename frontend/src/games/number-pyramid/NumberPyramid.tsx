import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import type { HouseKey } from '../../design/tokens';
import { GameShell, type FeedbackState } from '../../shell';
import styles from './NumberPyramid.module.css';
import { at, cellIndex, fillOrder, generateRound, getHint, isSolved, type Puzzle } from './pyramid';

export interface NumberPyramidProps {
  /** Decides the puzzles. The same seed always gives the same round. */
  seed: number;
  house?: HouseKey;
  /** Leaves the game; shown as the shell's "Games" button. */
  onExit?: () => void;
}

const INSTRUCTION = 'Every block is the sum of the two blocks below it. Fill the empty blocks!';

/** Which tile (index into puzzle.tiles) sits in each block; null for givens and empty blocks. */
type Placements = (number | null)[];

const emptyPlacements = (puzzle: Puzzle): Placements => puzzle.solution.map(() => null);

/** The next empty block in fill order, starting just after `after` and wrapping around. */
function firstEmpty(puzzle: Puzzle, placements: Placements, after?: number): number | null {
  const order = fillOrder(puzzle.rows);
  const start = after === undefined ? 0 : order.indexOf(after) + 1;
  for (let offset = 0; offset < order.length; offset++) {
    const cell = at(order, (start + offset) % order.length);
    if (!puzzle.given[cell] && placements[cell] === null) return cell;
  }
  return null;
}

export function NumberPyramid({ seed, house = 'builders', onExit }: NumberPyramidProps) {
  const [round, setRound] = useState(0);
  const [index, setIndex] = useState(0);
  const puzzles = useMemo(() => generateRound(seed + round), [seed, round]);
  const puzzle = at(puzzles, index);

  const [placements, setPlacements] = useState<Placements>(() => emptyPlacements(puzzle));
  const [selected, setSelected] = useState<number | null>(() =>
    firstEmpty(puzzle, emptyPlacements(puzzle)),
  );
  const [hint, setHint] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState>('idle');

  const lastPuzzle = index === puzzles.length - 1;

  // Show "correct" for a moment, then the completion screen (the round one after the last puzzle).
  useEffect(() => {
    if (feedback !== 'correct') return;
    const timer = window.setTimeout(() => setFeedback(lastPuzzle ? 'complete' : 'solved'), 1100);
    return () => window.clearTimeout(timer);
  }, [feedback, lastPuzzle]);

  const entries = placements.map((tile) => (tile === null ? null : at(puzzle.tiles, tile)));
  const locked = feedback !== 'idle' && feedback !== 'incorrect';
  const complete = firstEmpty(puzzle, placements) === null;
  const usedTiles = new Set(placements.filter((tile) => tile !== null));

  const start = (next: Puzzle) => {
    const fresh = emptyPlacements(next);
    setPlacements(fresh);
    setSelected(firstEmpty(next, fresh));
    setHint(null);
    setFeedback('idle');
  };

  const answerChanged = (next: Placements, nextSelected: number | null) => {
    setPlacements(next);
    setSelected(nextSelected);
    setHint(null);
    setFeedback('idle');
  };

  const tapBlock = (cell: number) => {
    if (locked) return;
    if (placements[cell] === null) {
      setSelected(cell);
      return;
    }
    // Tapping a filled block sends its tile back to the tray.
    const next = [...placements];
    next[cell] = null;
    answerChanged(next, cell);
  };

  const tapTile = (tile: number) => {
    if (locked || usedTiles.has(tile)) return;
    const cell = selected ?? firstEmpty(puzzle, placements);
    if (cell === null) return;
    const next = [...placements];
    next[cell] = tile;
    answerChanged(next, firstEmpty(puzzle, next, cell));
  };

  const check = () => setFeedback(isSolved(puzzle, entries) ? 'correct' : 'incorrect');

  const next = () => {
    if (!lastPuzzle) {
      setIndex(index + 1);
      start(at(puzzles, index + 1));
      return;
    }
    // "Play again" on the round-complete screen: a new round with fresh puzzles.
    const nextRound = round + 1;
    setRound(nextRound);
    setIndex(0);
    start(at(generateRound(seed + nextRound), 0));
  };

  const rows = Array.from({ length: puzzle.rows }, (_, row) =>
    Array.from({ length: row + 1 }, (_, col) => cellIndex(row, col)),
  );

  return (
    <GameShell
      title="Number Pyramid"
      instruction={INSTRUCTION}
      house={house}
      progress={{ current: index + 1, total: puzzles.length }}
      feedback={feedback}
      hint={hint}
      onHint={locked ? undefined : () => setHint(getHint(puzzle, entries))}
      onCheck={complete && !locked ? check : undefined}
      onReset={locked ? undefined : () => start(puzzle)}
      onNext={next}
      onExit={onExit}
    >
      <div className={styles.game}>
        <div
          className={styles.pyramid}
          role="group"
          aria-label="Number pyramid"
          style={{ '--rows': puzzle.rows } as CSSProperties}
        >
          {rows.map((cells, row) => (
            <div key={row} className={styles.row}>
              {cells.map((cell, col) => {
                const place = `row ${row + 1}, place ${col + 1}`;
                if (puzzle.given[cell]) {
                  return (
                    <div key={cell} className={styles.block} data-kind="given">
                      <span className={styles.srOnly}>{`Block, ${place}: `}</span>
                      {puzzle.solution[cell]}
                    </div>
                  );
                }
                const value = entries[cell];
                return (
                  <button
                    key={cell}
                    type="button"
                    className={styles.block}
                    data-kind={value === null ? 'empty' : 'filled'}
                    aria-pressed={selected === cell}
                    aria-label={
                      value === null
                        ? `Empty block, ${place}`
                        : `Block with ${value}, ${place}. Tap to take it out`
                    }
                    onClick={() => tapBlock(cell)}
                  >
                    {value}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className={styles.tray} role="group" aria-label="Number tiles">
          {puzzle.tiles.map((value, tile) => {
            const used = usedTiles.has(tile);
            return (
              <button
                key={tile}
                type="button"
                className={styles.tile}
                // Stays focusable when used, so keyboard focus is not lost after placing.
                aria-disabled={used}
                aria-label={used ? `${value}, already placed` : `Place ${value}`}
                onClick={() => tapTile(tile)}
              >
                {value}
              </button>
            );
          })}
        </div>
      </div>
    </GameShell>
  );
}
