import { describe, expect, it } from 'vitest';
import type { Equation } from '../../api/puzzles';
import { CHAIN, SAME_VALUE_TWICE } from '../../test/puzzleBackend';
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
  it("turns the API's side and index into a position in reading order", () => {
    // □ − 3 = 5: the 3 is the third token on the left.
    expect(linkedTokenIndex(eq(subtractFromBox), { side: 'left', index: 2 })).toBe(2);
    // 14 − □ = 8: the 8 is the first token on the right, after three on the left.
    expect(linkedTokenIndex(eq(subtractBox), { side: 'right', index: 0 })).toBe(3);
    // 20 = 6 + □: the 6 is the first token on the right, after one on the left.
    expect(linkedTokenIndex(eq(answerLeft), { side: 'right', index: 0 })).toBe(1);
    expect(linkedTokenIndex(eq(answerLeft), { side: 'left', index: 0 })).toBe(0);
  });

  it('gives -1 for a first step, which has no link', () => {
    expect(linkedTokenIndex(eq(addMissing), null)).toBe(-1);
  });

  it('tells two equal numbers apart instead of guessing', () => {
    const twice = eq(SAME_VALUE_TWICE[1]?.equation); // □ − 9 = 9
    const { tokens } = equationParts(twice);

    const left = linkedTokenIndex(twice, { side: 'left', index: 2 });
    const right = linkedTokenIndex(twice, { side: 'right', index: 0 });

    expect([left, right]).toEqual([2, 3]);
    expect(tokens[left]).toEqual({ kind: 'number', value: 9 });
    expect(tokens[right]).toEqual({ kind: 'number', value: 9 });
  });
});
