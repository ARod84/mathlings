/*
 * Puzzle logic for Number Pyramid. Pure functions, no React.
 *
 * A pyramid with `rows` rows is stored as a flat array, top block first:
 * row r (0 = top) holds r + 1 blocks, and block (r, c) lives at
 * r * (r + 1) / 2 + c. Every block is the sum of the two blocks below it.
 */

export type Rng = () => number;

/** Array read that fails loudly instead of returning undefined. */
export function at<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`No item at index ${index}`);
  return item;
}

/** Small seeded generator (mulberry32), so a seed always gives the same puzzles. */
export function createRng(seed: number): Rng {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface Level {
  rows: number;
  /** Bottom-row numbers are drawn from 1..maxBase. */
  maxBase: number;
  /** false: the bottom row is given (adding only). true: givens are scattered (adding and subtracting). */
  mixed: boolean;
}

/** One round, easiest first. */
export const LEVELS: readonly Level[] = [
  { rows: 3, maxBase: 5, mixed: false },
  { rows: 3, maxBase: 9, mixed: false },
  { rows: 3, maxBase: 9, mixed: true },
  { rows: 3, maxBase: 12, mixed: true },
  { rows: 4, maxBase: 5, mixed: false },
  { rows: 4, maxBase: 9, mixed: false },
  { rows: 4, maxBase: 9, mixed: true },
  { rows: 4, maxBase: 12, mixed: true },
];

export interface Puzzle {
  rows: number;
  /** The full, correct pyramid. */
  solution: number[];
  /** Which blocks are shown from the start. */
  given: boolean[];
  /** Number tiles the child can place: every missing number plus a few extras, ascending. */
  tiles: number[];
}

/** [parent, left child, right child] as flat indexes. */
export type Triple = readonly [number, number, number];

export const cellCount = (rows: number): number => (rows * (rows + 1)) / 2;
export const cellIndex = (row: number, col: number): number => (row * (row + 1)) / 2 + col;

/**
 * The order empty blocks are offered in: bottom row first, left to right.
 * That is the order a pyramid is usually worked out in.
 */
export function fillOrder(rows: number): number[] {
  const order: number[] = [];
  for (let row = rows - 1; row >= 0; row--) {
    for (let col = 0; col <= row; col++) order.push(cellIndex(row, col));
  }
  return order;
}

export function triples(rows: number): Triple[] {
  const result: Triple[] = [];
  for (let row = 0; row < rows - 1; row++) {
    for (let col = 0; col <= row; col++) {
      result.push([cellIndex(row, col), cellIndex(row + 1, col), cellIndex(row + 1, col + 1)]);
    }
  }
  return result;
}

/**
 * True when every block can be worked out one step at a time: each step uses
 * a parent and its two children where exactly one of the three is unknown.
 * A puzzle that passes has exactly one solution and never needs guessing.
 */
export function canDeduceAll(rows: number, known: readonly boolean[]): boolean {
  const state = [...known];
  const all = triples(rows);
  let progressed = true;
  while (progressed) {
    progressed = false;
    for (const triple of all) {
      const unknown = triple.filter((cell) => !state[cell]);
      if (unknown.length === 1) {
        state[at(unknown, 0)] = true;
        progressed = true;
      }
    }
  }
  return state.every(Boolean);
}

const randomInt = (rng: Rng, min: number, max: number): number =>
  min + Math.floor(rng() * (max - min + 1));

function shuffled<T>(items: readonly T[], rng: Rng): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = randomInt(rng, 0, i);
    [result[i], result[j]] = [at(result, j), at(result, i)];
  }
  return result;
}

function chooseGiven(level: Level, rng: Rng): boolean[] {
  const { rows } = level;
  const count = cellCount(rows);
  const baseStart = cellIndex(rows - 1, 0);
  const baseOnly = Array.from({ length: count }, (_, cell) => cell >= baseStart);
  if (!level.mixed) return baseOnly;

  const cells = Array.from({ length: count }, (_, cell) => cell);
  for (let attempt = 0; attempt < 300; attempt++) {
    const picked = new Set(shuffled(cells, rng).slice(0, rows));
    const given = cells.map((cell) => picked.has(cell));
    const allInBase = [...picked].every((cell) => cell >= baseStart);
    if (!allInBase && canDeduceAll(rows, given)) return given;
  }
  return baseOnly;
}

function chooseTiles(solution: number[], given: boolean[], rng: Rng): number[] {
  const missing = solution.filter((_, cell) => !given[cell]);
  const taken = new Set(missing);
  const extras: number[] = [];
  const wanted = missing.length > 3 ? 3 : 2;
  for (let attempt = 0; attempt < 200 && extras.length < wanted; attempt++) {
    const near = at(missing, randomInt(rng, 0, missing.length - 1));
    const candidate = near + randomInt(rng, 1, 3) * (rng() < 0.5 ? -1 : 1);
    if (candidate > 0 && !taken.has(candidate)) {
      taken.add(candidate);
      extras.push(candidate);
    }
  }
  return [...missing, ...extras].sort((a, b) => a - b);
}

export function generatePuzzle(level: Level, rng: Rng): Puzzle {
  const { rows } = level;
  const solution = new Array<number>(cellCount(rows)).fill(0);
  for (let col = 0; col < rows; col++) {
    solution[cellIndex(rows - 1, col)] = randomInt(rng, 1, level.maxBase);
  }
  for (let row = rows - 2; row >= 0; row--) {
    for (let col = 0; col <= row; col++) {
      solution[cellIndex(row, col)] =
        at(solution, cellIndex(row + 1, col)) + at(solution, cellIndex(row + 1, col + 1));
    }
  }
  const given = chooseGiven(level, rng);
  return { rows, solution, given, tiles: chooseTiles(solution, given, rng) };
}

/** The puzzles of one round, one per level. */
export function generateRound(seed: number): Puzzle[] {
  const rng = createRng(seed);
  return LEVELS.map((level) => generatePuzzle(level, rng));
}

/** `entries` holds what the child placed in each block (null for givens and empty blocks). */
export function isSolved(puzzle: Puzzle, entries: readonly (number | null)[]): boolean {
  return puzzle.solution.every((value, cell) => puzzle.given[cell] || entries[cell] === value);
}

export const RULE_HINT = 'Every block is the sum of the two blocks right below it.';

/**
 * A hint for the next step, built from the blocks that are right so far.
 * It points at one block and asks the sum; it never gives the answer. If the
 * block it points at already holds a wrong number, it asks for another look.
 */
export function getHint(puzzle: Puzzle, entries: readonly (number | null)[]): string {
  const { solution, given } = puzzle;
  const known = solution.map((value, cell) => given[cell] || entries[cell] === value);
  if (known.every(Boolean)) return 'Every block fits. Tap Check!';

  let step: { triple: Triple; target: number } | null = null;
  for (const triple of triples(puzzle.rows)) {
    const unknown = triple.filter((cell) => !known[cell]);
    if (unknown.length !== 1) continue;
    const target = at(unknown, 0);
    const misplaced = entries[target] !== null;
    // A wrong number is the most useful thing to point at, so it wins.
    if (step === null || misplaced) step = { triple, target };
    if (misplaced) break;
  }
  if (step === null) return RULE_HINT;

  const [parent, left, right] = step.triple;
  const retry = entries[step.target] !== null;

  if (step.target === parent) {
    const a = at(solution, left);
    const b = at(solution, right);
    return retry
      ? `Take another look at the block resting on ${a} and ${b}. What is ${a} + ${b}?`
      : `Look at the blocks ${a} and ${b}. The block resting on them is their sum. What is ${a} + ${b}?`;
  }

  const top = at(solution, parent);
  const side = at(solution, step.target === left ? right : left);
  return retry
    ? `Take another look at the block next to ${side}, under ${top}. What do you add to ${side} to make ${top}?`
    : `The block ${top} rests on ${side} and an empty block. What do you add to ${side} to make ${top}?`;
}
