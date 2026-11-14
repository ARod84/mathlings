import { describe, expect, it } from 'vitest';
import { blankLabel, cellKey, cellsOfLine, gridDescription, onLine } from './grid';

describe('gridDescription', () => {
  it('reads the grid row by row with its targets, then the column targets', () => {
    expect(
      gridDescription(
        [
          [3, null],
          [null, 5],
        ],
        [9, 7],
        [5, 11],
      ),
    ).toBe('Row 1: 3, blank. Target 9. Row 2: blank, 5. Target 7. Column targets: 5, 11.');
  });

  it('reads a solved blank as its number', () => {
    const solved = new Map([[cellKey(0, 1), 6]]);
    expect(
      gridDescription(
        [
          [3, null],
          [null, 5],
        ],
        [9, 7],
        [5, 11],
        solved,
      ),
    ).toBe('Row 1: 3, 6. Target 9. Row 2: blank, 5. Target 7. Column targets: 5, 11.');
  });

  it('handles a 3 by 3 with two-digit numbers', () => {
    const cells = [
      [20, 37, null],
      [null, 40, 22],
      [31, null, null],
    ];
    expect(gridDescription(cells, [85, 77, 73], [66, 89, 80])).toBe(
      'Row 1: 20, 37, blank. Target 85. Row 2: blank, 40, 22. Target 77. ' +
        'Row 3: 31, blank, blank. Target 73. Column targets: 66, 89, 80.',
    );
  });
});

describe('blankLabel', () => {
  it('names the place and the step, and the picked number once there is one', () => {
    expect(blankLabel({ row: 0, col: 1 }, 0, 3, null)).toBe('Row 1, column 2. Blank 1 of 3.');
    expect(blankLabel({ row: 2, col: 0 }, 2, 3, 15)).toBe(
      'Row 3, column 1. Blank 3 of 3, with 15.',
    );
  });
});

describe('lines', () => {
  it('lists the cells of a row or a column in order', () => {
    expect(cellsOfLine({ kind: 'row', index: 1 }, 3)).toEqual([
      { row: 1, col: 0 },
      { row: 1, col: 1 },
      { row: 1, col: 2 },
    ]);
    expect(cellsOfLine({ kind: 'col', index: 2 }, 2)).toEqual([
      { row: 0, col: 2 },
      { row: 1, col: 2 },
    ]);
  });

  it('says whether a cell is on a line', () => {
    expect(onLine({ kind: 'row', index: 0 }, { row: 0, col: 2 })).toBe(true);
    expect(onLine({ kind: 'row', index: 0 }, { row: 1, col: 0 })).toBe(false);
    expect(onLine({ kind: 'col', index: 1 }, { row: 2, col: 1 })).toBe(true);
    expect(onLine({ kind: 'col', index: 1 }, { row: 1, col: 0 })).toBe(false);
  });
});
