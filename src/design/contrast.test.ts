import { describe, expect, it } from 'vitest';
import { AA_NORMAL_TEXT, contrastRatio } from './contrast';
import { HOUSE_KEYS, color, house } from './tokens';

/** [description, text color, background color] */
type Pairing = [string, string, string];

function expectReadable([, text, background]: Pairing) {
  expect(contrastRatio(text, background)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
}

describe('contrastRatio', () => {
  it('matches the WCAG reference values', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5);
    expect(contrastRatio('#767676', '#ffffff')).toBeGreaterThanOrEqual(4.5);
  });
});

describe('text contrast (WCAG AA, 4.5:1 at normal text size)', () => {
  const onBackdrop: Pairing[] = [
    ['white on space', color.onDark, color.space],
    ['white on space-2', color.onDark, color.space2],
    ['muted text on space', color.onDarkMuted, color.space],
    ['muted text on space-2', color.onDarkMuted, color.space2],
    ['gold on space', color.gold, color.space],
    ['gold on space-2', color.gold, color.space2],
  ];
  it.each(onBackdrop)('body text on the backdrop: %s', (...pairing) => expectReadable(pairing));

  const onLightSurfaces: Pairing[] = [
    ['ink on paper', color.ink, color.paper],
    ['ink on cream', color.ink, color.cream],
    ['secondary ink on paper', color.ink2, color.paper],
    ['secondary ink on cream', color.ink2, color.cream],
    ['space on cream', color.space, color.cream],
  ];
  it.each(onLightSurfaces)('text on light surfaces: %s', (...pairing) => expectReadable(pairing));

  const onGold: Pairing[] = [
    ['ink on gold', color.ink, color.gold],
    ['space on gold', color.space, color.gold],
    ['ink on deep gold', color.ink, color.goldDeep],
  ];
  it.each(onGold)('text on gold: %s', (...pairing) => expectReadable(pairing));

  const feedback: Pairing[] = [
    ['correct message', color.correctText, color.correctBg],
    ['try-again message', color.retryText, color.retryBg],
  ];
  it.each(feedback)('feedback text: %s', (...pairing) => expectReadable(pairing));

  describe.each(HOUSE_KEYS)('house: %s', (key) => {
    const palette = house[key];
    const pairings: Pairing[] = [
      ['white on strong', color.onDark, palette.strong],
      ['white on dark (header gradient start)', color.onDark, palette.dark],
      ['strong on white', palette.strong, color.paper],
      ['strong on cream', palette.strong, color.cream],
      ['strong on soft tint', palette.strong, palette.soft],
    ];
    it.each(pairings)('%s', (...pairing) => expectReadable(pairing));
  });

  it('keeps the reason for -strong visible: base house colors are not text-safe', () => {
    const failing = HOUSE_KEYS.filter(
      (key) => contrastRatio(color.onDark, house[key].base) < AA_NORMAL_TEXT,
    );
    // If this changes, the house palette changed: revisit which shade carries text.
    expect(failing).toEqual(['builders', 'cultivators', 'artisans', 'scientists']);
  });
});
