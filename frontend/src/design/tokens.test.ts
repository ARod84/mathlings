import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  HOUSE_KEYS,
  color,
  duration,
  easing,
  fontFamily,
  fontSize,
  fontWeight,
  house,
  letterSpacing,
  lineHeight,
  radius,
  shadow,
  size,
  space,
} from './tokens';

// Read from disk: Vitest does not process CSS imports by default.
const css = readFileSync(resolve(import.meta.dirname, 'tokens.css'), 'utf8');

function declarations(block: string): Map<string, string> {
  const map = new Map<string, string>();
  const withoutComments = block.replace(/\/\*[\s\S]*?\*\//g, '');
  for (const match of withoutComments.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const [, name, value] = match;
    if (name && value) map.set(name, value.trim().replace(/\s+/g, ' '));
  }
  return map;
}

const rootBlock = /:root\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? '';
const root = declarations(rootBlock);

const kebab = (key: string) => key.replace(/([a-z])([A-Z0-9])/g, '$1-$2').toLowerCase();

function group(prefix: string, values: Record<string, string | number>, unit = '') {
  return Object.entries(values).map(
    ([key, value]) => [`--${prefix}-${kebab(key)}`, `${value}${unit}`] as const,
  );
}

const expected: (readonly [string, string])[] = [
  ...group('color', color),
  ...HOUSE_KEYS.flatMap((key) => [
    [`--house-${key}`, house[key].base] as const,
    [`--house-${key}-dark`, house[key].dark] as const,
    [`--house-${key}-soft`, house[key].soft] as const,
    [`--house-${key}-strong`, house[key].strong] as const,
  ]),
  ...group('font', fontFamily),
  ...group('font-weight', fontWeight),
  ...group('font-size', fontSize),
  ...group('line-height', lineHeight),
  ...group('letter-spacing', letterSpacing),
  ...group('space', space),
  ...group('size', size),
  ...group('radius', radius),
  ...group('shadow', shadow),
  ...group('duration', duration, 'ms'),
  ...group('ease', easing),
];

describe('tokens.ts mirrors tokens.css', () => {
  it.each(expected)('%s', (name, value) => {
    expect(root.get(name)).toBe(value);
  });

  it('switches the active house with [data-house]', () => {
    for (const key of HOUSE_KEYS) {
      expect(css).toContain(`[data-house='${key}']`);
    }
  });
});

describe('reduced motion', () => {
  const reducedBlock =
    /@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*)\}\s*$/.exec(css)?.[1] ?? '';
  const reduced = declarations(reducedBlock);

  it.each(Object.keys(duration))('--duration-%s falls back to roughly zero', (key) => {
    const value = reduced.get(`--duration-${key}`);
    expect(value).toBeDefined();
    expect(parseFloat(value ?? '')).toBeLessThanOrEqual(1);
    expect(value).toMatch(/ms$/);
  });
});
