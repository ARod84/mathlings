/*
 * Reading a "Next in Line" row: how a number is written and spoken, what the
 * row says to a screen reader, and which jumps may be drawn as a hint.
 *
 * A row comes from the API as its terms in order, with null where a term is
 * blank. The answers are never here: a blank is filled in only with what the
 * child has already got right.
 */

/** The real minus sign, U+2212. A hyphen is not a minus. */
export const MINUS = '−';

/** A number as it is written on a block or a tile: −3, not -3. */
export function formatNumber(value: number): string {
  return value < 0 ? `${MINUS}${-value}` : String(value);
}

/** A number as a screen reader should say it: "minus 3". */
export function spokenNumber(value: number): string {
  return value < 0 ? `minus ${-value}` : String(value);
}

/**
 * The row in words: "4, 8, 12, blank, 20". `solved` maps the position of a
 * blank the child has solved to its number, and that blank is then read as
 * the number: "4, 8, 12, 16, 20".
 */
export function rowLabel(
  terms: readonly (number | null)[],
  solved: ReadonlyMap<number, number> = new Map(),
): string {
  return terms
    .map((term, position) => {
      const value = term ?? solved.get(position);
      return value === undefined ? 'blank' : spokenNumber(value);
    })
    .join(', ');
}

/** A jump from one term to the next one, both on show. */
export interface Jump {
  /** Position of the term the jump starts from; it lands on the next one. */
  from: number;
  difference: number;
}

/**
 * The jumps that may be drawn over a row: only between two neighbouring terms
 * the puzzle itself shows. A jump into or out of a blank would say what the
 * blank is, so there is none, and that holds for a blank the child has solved
 * too: `terms` is the row as the server sent it.
 */
export function visibleJumps(terms: readonly (number | null)[]): Jump[] {
  const jumps: Jump[] = [];
  for (let from = 0; from < terms.length - 1; from += 1) {
    const here = terms[from];
    const next = terms[from + 1];
    if (here === null || here === undefined || next === null || next === undefined) continue;
    jumps.push({ from, difference: next - here });
  }
  return jumps;
}

/** A jump's label: "+4", or "−3" with the real minus sign. */
export function formatJump(difference: number): string {
  return difference < 0 ? `${MINUS}${-difference}` : `+${difference}`;
}
