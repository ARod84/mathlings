import { describe, expect, it } from 'vitest';
import {
  LEVELS,
  at,
  canDeduceAll,
  cellCount,
  cellIndex,
  generateRound,
  getHint,
  isSolved,
  triples,
  type Puzzle,
} from './pyramid';

const SEEDS = Array.from({ length: 200 }, (_, seed) => seed);

describe('generateRound', () => {
  it('gives the same puzzles for the same seed', () => {
    expect(generateRound(42)).toEqual(generateRound(42));
    expect(generateRound(42)).not.toEqual(generateRound(43));
  });

  it('builds valid pyramids that can be solved step by step, for many seeds', () => {
    for (const seed of SEEDS) {
      const round = generateRound(seed);
      expect(round).toHaveLength(LEVELS.length);
      round.forEach((puzzle, i) => {
        const level = at(LEVELS, i);
        expect(puzzle.rows).toBe(level.rows);
        expect(puzzle.solution).toHaveLength(cellCount(level.rows));
        for (const [parent, left, right] of triples(puzzle.rows)) {
          expect(at(puzzle.solution, parent)).toBe(
            at(puzzle.solution, left) + at(puzzle.solution, right),
          );
        }
        for (let col = 0; col < level.rows; col++) {
          const base = puzzle.solution[cellIndex(level.rows - 1, col)];
          expect(base).toBeGreaterThanOrEqual(1);
          expect(base).toBeLessThanOrEqual(level.maxBase);
        }
        expect(puzzle.given.filter(Boolean)).toHaveLength(level.rows);
        expect(canDeduceAll(puzzle.rows, puzzle.given)).toBe(true);
      });
    }
  });

  it('offers every missing number as a tile, plus extras that are not answers', () => {
    for (const seed of SEEDS) {
      for (const puzzle of generateRound(seed)) {
        const missing = puzzle.solution.filter((_, cell) => !puzzle.given[cell]);
        const pool = [...puzzle.tiles];
        for (const value of missing) {
          const at = pool.indexOf(value);
          expect(at).toBeGreaterThanOrEqual(0);
          pool.splice(at, 1);
        }
        expect(pool.length).toBeGreaterThanOrEqual(1);
        for (const extra of pool) {
          expect(extra).toBeGreaterThan(0);
          expect(missing).not.toContain(extra);
        }
        expect(puzzle.tiles).toEqual([...puzzle.tiles].sort((a, b) => a - b));
      }
    }
  });
});

describe('canDeduceAll', () => {
  it('accepts a full bottom row and rejects sets that need guessing', () => {
    expect(canDeduceAll(3, [false, false, false, true, true, true])).toBe(true);
    expect(canDeduceAll(3, [true, false, false, true, false, true])).toBe(false);
    expect(canDeduceAll(3, [true, true, false, false, false, true])).toBe(true);
  });
});

//        8
//      3   5
//    1   2   3
const base: Puzzle = {
  rows: 3,
  solution: [8, 3, 5, 1, 2, 3],
  given: [false, false, false, true, true, true],
  tiles: [3, 4, 5, 7, 8],
};
const mixed: Puzzle = { ...base, given: [true, true, false, false, false, true] };

describe('isSolved', () => {
  it('needs every empty block to hold the right number', () => {
    expect(isSolved(base, [8, 3, 5, null, null, null])).toBe(true);
    expect(isSolved(base, [8, 5, 3, null, null, null])).toBe(false);
    expect(isSolved(base, [8, 3, null, null, null, null])).toBe(false);
  });
});

describe('getHint', () => {
  it('points at the next sum without giving the answer', () => {
    const hint = getHint(base, [null, null, null, null, null, null]);
    expect(hint).toContain('What is 1 + 2?');
    expect(hint).not.toContain('3.');
  });

  it('asks for a missing addend when the block below is empty', () => {
    expect(getHint(mixed, [null, null, null, null, null, null])).toBe(
      'The block 8 rests on 3 and an empty block. What do you add to 3 to make 8?',
    );
  });

  it('asks for another look at a wrong number first', () => {
    expect(getHint(base, [null, 3, 4, null, null, null])).toBe(
      'Take another look at the block resting on 2 and 3. What is 2 + 3?',
    );
    expect(getHint(mixed, [null, null, 4, null, null, null])).toBe(
      'Take another look at the block next to 3, under 8. What do you add to 3 to make 8?',
    );
  });

  it('sends the child to Check when everything fits', () => {
    expect(getHint(base, [8, 3, 5, null, null, null])).toBe('Every block fits. Tap Check!');
  });
});
