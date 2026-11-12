/**
 * Typed mirror of tokens.css. tokens.test.ts fails if the two drift apart,
 * so change both files together.
 */

export const HOUSE_KEYS = [
  'navigators',
  'builders',
  'cultivators',
  'artisans',
  'scientists',
] as const;

export type HouseKey = (typeof HOUSE_KEYS)[number];

export interface HousePalette {
  /** The house color. Decoration only: white text on it fails WCAG AA for most houses. */
  base: string;
  /** Gradient partner for the base color. */
  dark: string;
  /** Pale tint for bubbles and selected states. */
  soft: string;
  /** Text-safe shade: at least 4.5:1 against white. */
  strong: string;
}

export const color = {
  space: '#3a1e63',
  space2: '#5a2e8c',
  space3: '#6e3aa0',
  gold: '#ffcb45',
  goldDeep: '#f6b53c',
  ink: '#3b2a4d',
  ink2: '#6e5680',
  onDark: '#ffffff',
  onDarkMuted: '#d8ccf2',
  outline: '#221739',
  paper: '#ffffff',
  cream: '#fbeff6',
  sand: '#f6e2ee',
  line: '#f0dee9',
  magenta: '#ec4d92',
  peach: '#f59a6b',
  lavender: '#a98ce0',
  mint: '#34c79a',
  correctBg: '#e2f3e8',
  correctText: '#235c3b',
  retryBg: '#fbeee2',
  retryText: '#8a4d1b',
} as const;

export const house: Record<HouseKey, HousePalette> = {
  navigators: { base: '#7c4def', dark: '#5e2fd0', soft: '#ede6fe', strong: '#5226b5' },
  builders: { base: '#e86e48', dark: '#c4542f', soft: '#fce7dc', strong: '#a8481f' },
  cultivators: { base: '#15a589', dark: '#0e7e68', soft: '#dbf5ee', strong: '#0b6b58' },
  artisans: { base: '#e94e8e', dark: '#cb3a75', soft: '#fce2ee', strong: '#b22c66' },
  scientists: { base: '#1f9bb5', dark: '#137f97', soft: '#dcf1f6', strong: '#0f6276' },
};

export const fontFamily = {
  pop: "'Outfit', system-ui, sans-serif",
  display: "'Outfit', system-ui, sans-serif",
  body: "'Lexend', system-ui, sans-serif",
  reading: "'Lexend', system-ui, sans-serif",
} as const;

export const fontWeight = {
  regular: 400,
  medium: 500,
  bold: 700,
  heavy: 800,
} as const;

export const fontSize = {
  xs: '0.75rem',
  sm: '0.8125rem',
  md: '0.9375rem',
  lg: '1.0625rem',
  xl: '1.3125rem',
  '2xl': '1.625rem',
  '3xl': '2.125rem',
  display: '2.5rem',
} as const;

export const lineHeight = {
  tight: 1.1,
  snug: 1.25,
  body: 1.55,
} as const;

export const letterSpacing = {
  label: '0.12em',
} as const;

/** 4 px base scale; the key is the multiplier. */
export const space = {
  1: '0.25rem',
  2: '0.5rem',
  3: '0.75rem',
  4: '1rem',
  5: '1.25rem',
  6: '1.5rem',
  8: '2rem',
  10: '2.5rem',
  12: '3rem',
  16: '4rem',
} as const;

export const size = {
  touchMin: '2.75rem',
  control: '3.25rem',
  outline: '3px',
  press: '4px',
} as const;

export const radius = {
  sm: '0.375rem',
  md: '0.5rem',
  lg: '0.75rem',
  xl: '1rem',
  pill: '999px',
} as const;

/** Hard-edged, no blur. */
export const shadow = {
  tile: '0 4px 0 0 var(--color-outline)',
  soft: '4px 4px 0 0 rgba(34, 23, 57, 0.3)',
  card: '6px 6px 0 0 rgba(34, 23, 57, 0.3)',
  panel: '8px 8px 0 0 rgba(20, 10, 40, 0.55)',
  button: '0 5px 0 0 var(--color-outline)',
} as const;

/** Durations in milliseconds. Under prefers-reduced-motion the CSS variables drop to ~0. */
export const duration = {
  fast: 120,
  base: 220,
  slow: 420,
  celebrate: 900,
  float: 4500,
  twinkle: 3000,
} as const;

export const easing = {
  standard: 'cubic-bezier(0.2, 0, 0, 1)',
  out: 'cubic-bezier(0.16, 1, 0.3, 1)',
  bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  ambient: 'ease-in-out',
} as const;

export type ColorToken = keyof typeof color;
export type FontFamilyToken = keyof typeof fontFamily;
export type FontSizeToken = keyof typeof fontSize;
export type SpaceToken = keyof typeof space;
export type RadiusToken = keyof typeof radius;
export type ShadowToken = keyof typeof shadow;
export type DurationToken = keyof typeof duration;
export type EasingToken = keyof typeof easing;

export const tokens = {
  color,
  house,
  fontFamily,
  fontWeight,
  fontSize,
  lineHeight,
  letterSpacing,
  space,
  size,
  radius,
  shadow,
  duration,
  easing,
} as const;
