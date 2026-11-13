import { describe, expect, it } from 'vitest';
import type { Equation } from '../../api/puzzles';
import { CHAIN } from '../../test/puzzleBackend';
import { equationLabel, equationParts, linkedTokenIndex } from './equation';

const [addMissing, subtractFromBox, subtractBox, answerLeft] = CHAIN.map((step) => step.equation);
const eq = (equation: Equation | undefined): Equation => {
  if (!equation) throw new Error('missing fixture equation');
  return equation;
};

describe('equationLabel', () => {
  it('reads every form naturally, with the box as "box"', () => {
    expect(equationLabel(eq(addMissing))).toBe('8 plus box equals 11');
    expect(equationLabel(eq(subtractFromBox))).toBe('box minus 3 equals 5');
    expect(equationLabel(eq(subtractBox))).toBe('14 minus box equals 8');
    expect(equationLabel(eq(answerLeft))).toBe('20 equals 6 plus box');
  });

  it('says what is in the box while the child is still deciding', () => {
    expect(equationLabel(eq(addMissing), 3)).toBe('8 plus box with 3 equals 11');
    expect(equationLabel(eq(answerLeft), 14)).toBe('20 equals 6 plus box with 14');
  });

  it('reads a solved step as the finished sum', () => {
    expect(equationLabel(eq(addMissing), 3, true)).toBe('8 plus 3 equals 11');
    expect(equationLabel(eq(subtractFromBox), 8, true)).toBe('8 minus 3 equals 5');
  });
});

describe('equationParts', () => {
  it('lists the tokens in reading order and says where the equals sign goes', () => {
    expect(equationParts(eq(addMissing))).toEqual({
      tokens: [
        { kind: 'number', value: 8 },
        { kind: 'operator', symbol: '+' },
        { kind: 'unknown' },
        { kind: 'number', value: 11 },
      ],
      equalsAt: 3,
    });
    expect(equationParts(eq(answerLeft)).equalsAt).toBe(1);
  });
});

describe('linkedTokenIndex', () => {
  it('finds the visible number that is the previous answer', () => {
    // □ − 3 = 5 after answering 3.
    expect(linkedTokenIndex(eq(subtractFromBox), 3)).toBe(2);
    // 14 − □ = 8 after answering 8.
    expect(linkedTokenIndex(eq(subtractBox), 8)).toBe(3);
  });

  it('gives -1 for the first step or when the number is not there', () => {
    expect(linkedTokenIndex(eq(addMissing), null)).toBe(-1);
    expect(linkedTokenIndex(eq(addMissing), 99)).toBe(-1);
  });

  it('picks the first when both visible numbers match', () => {
    const doubled: Equation = {
      left: [{ kind: 'unknown' }, { kind: 'operator', symbol: '-' }, { kind: 'number', value: 5 }],
      right: [{ kind: 'number', value: 5 }],
    };
    expect(linkedTokenIndex(doubled, 5)).toBe(2);
  });
});
