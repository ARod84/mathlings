import { describe, expect, it } from 'vitest';
import { formatJump, formatNumber, MINUS, rowLabel, spokenNumber, visibleJumps } from './sequence';

describe('numbers', () => {
  it('writes a negative number with the real minus sign, never a hyphen', () => {
    expect(MINUS).toBe('−');
    expect(formatNumber(-3)).toBe('−3');
    expect(formatNumber(-3)).not.toContain('-');
    expect(formatNumber(-50)).toBe('−50');
    expect(formatNumber(0)).toBe('0');
    expect(formatNumber(1000)).toBe('1000');
  });

  it('says a negative number as "minus 3"', () => {
    expect(spokenNumber(-3)).toBe('minus 3');
    expect(spokenNumber(16)).toBe('16');
    expect(spokenNumber(0)).toBe('0');
  });
});

describe('rowLabel', () => {
  it('reads the row naturally, with "blank" for each blank', () => {
    expect(rowLabel([4, 8, 12, null, 20])).toBe('4, 8, 12, blank, 20');
    expect(rowLabel([45, 35, 25, null, null])).toBe('45, 35, 25, blank, blank');
  });

  it('reads a solved blank as its number', () => {
    expect(rowLabel([4, 8, 12, null, 20], new Map([[3, 16]]))).toBe('4, 8, 12, 16, 20');
    expect(rowLabel([45, 35, 25, null, null], new Map([[3, 15]]))).toBe('45, 35, 25, 15, blank');
  });

  it('says "minus" for numbers below zero, given or solved', () => {
    expect(rowLabel([3, 0, -3, null, null])).toBe('3, 0, minus 3, blank, blank');
    expect(rowLabel([9, 6, 3, 0, null], new Map([[4, -3]]))).toBe('9, 6, 3, 0, minus 3');
  });
});

describe('visibleJumps', () => {
  it('gives one jump per pair of neighbouring visible terms', () => {
    expect(visibleJumps([4, 8, 12, 16, null])).toEqual([
      { from: 0, difference: 4 },
      { from: 1, difference: 4 },
      { from: 2, difference: 4 },
    ]);
  });

  it('has no jump into or out of a blank, wherever the blank is', () => {
    // 50, □, 150, 200, 250, 300: nothing touches the second term.
    expect(visibleJumps([50, null, 150, 200, 250, 300]).map((jump) => jump.from)).toEqual([
      2, 3, 4,
    ]);
    // Two blanks next to each other.
    expect(visibleJumps([45, 35, 25, null, null]).map((jump) => jump.from)).toEqual([0, 1]);
    // Blanks apart: the term between them has a blank on both sides.
    expect(visibleJumps([50, null, 150, null, 250, 300]).map((jump) => jump.from)).toEqual([4]);
  });

  it('gives each jump of a growing sequence its own size', () => {
    expect(visibleJumps([1, 2, 4, 7, null]).map((jump) => jump.difference)).toEqual([1, 2, 3]);
  });

  it('gives a negative difference going down, through zero too', () => {
    expect(visibleJumps([9, 6, 3, 0, null]).map((jump) => jump.difference)).toEqual([-3, -3, -3]);
    expect(visibleJumps([3, 0, -3, null, null]).map((jump) => jump.difference)).toEqual([-3, -3]);
  });

  it('cannot give a value away: the answers are never among the terms it reads', () => {
    for (const terms of [
      [4, 8, 12, null, 20],
      [null, 8, 12, 16, 20],
      [1, null, 4, null, 11],
    ]) {
      for (const { from } of visibleJumps(terms)) {
        expect(terms[from]).not.toBeNull();
        expect(terms[from + 1]).not.toBeNull();
      }
    }
    expect(visibleJumps([1, null, 4, null, 11])).toEqual([]);
  });
});

describe('formatJump', () => {
  it('labels a jump with its sign, using the real minus', () => {
    expect(formatJump(4)).toBe('+4');
    expect(formatJump(-3)).toBe('−3');
    expect(formatJump(-3)).not.toContain('-');
    expect(formatJump(100)).toBe('+100');
  });
});
