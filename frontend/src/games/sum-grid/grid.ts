import type { components } from '../../api/schema';

/*
 * Reading a Sum Grid: what the grid says to a screen reader, and which cells
 * a line is made of. The cells come from the API with null where a cell is
 * blank; the answers are never here. A blank is filled in only with what the
 * child has already got right.
 */

export type Cell = components['schemas']['Cell'];
export type Line = components['schemas']['Line'];
export type GridCells = readonly (readonly (number | null)[])[];

/** A solved blank, by its place in the grid: "row,col" to the number found. */
export type Solved = ReadonlyMap<string, number>;

export const cellKey = (row: number, col: number): string => `${row},${col}`;

/** The cells a row or column runs through, in order. */
export function cellsOfLine(line: Line, size: number): Cell[] {
  return Array.from({ length: size }, (_, i) =>
    line.kind === 'row' ? { row: line.index, col: i } : { row: i, col: line.index },
  );
}

/** True if the cell is on the line. */
export function onLine(line: Line, cell: Cell): boolean {
  return line.kind === 'row' ? cell.row === line.index : cell.col === line.index;
}

/**
 * The grid in words, row by row, then the column targets:
 * "Row 1: 3, blank, 9. Target 18. Row 2: ... Column targets: 8, 11."
 * A solved blank is read as its number.
 */
export function gridDescription(
  cells: GridCells,
  rowTargets: readonly number[],
  colTargets: readonly number[],
  solved: Solved = new Map(),
): string {
  const rows = cells.map((row, r) => {
    const words = row.map((value, c) => {
      const known = value ?? solved.get(cellKey(r, c));
      return known === undefined ? 'blank' : String(known);
    });
    return `Row ${r + 1}: ${words.join(', ')}. Target ${rowTargets[r]}.`;
  });
  return `${rows.join(' ')} Column targets: ${colTargets.join(', ')}.`;
}

/** The current blank for a screen reader: "Row 1, column 2. Blank 1 of 3." */
export function blankLabel(
  cell: Cell,
  stepIndex: number,
  steps: number,
  selected: number | null,
): string {
  const place = `Row ${cell.row + 1}, column ${cell.col + 1}. Blank ${stepIndex + 1} of ${steps}`;
  return selected === null ? `${place}.` : `${place}, with ${selected}.`;
}
