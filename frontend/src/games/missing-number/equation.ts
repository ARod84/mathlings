import type { Equation, EquationToken, LinkedToken } from '../../api/puzzles';

/*
 * Reading an equation from its API tokens. Equations are never built from or
 * parsed out of strings: the tokens are the source of truth.
 */

/** Both sides in reading order, with where the equals sign goes. */
export function equationParts(equation: Equation): { tokens: EquationToken[]; equalsAt: number } {
  return { tokens: [...equation.left, ...equation.right], equalsAt: equation.left.length };
}

function tokenWords(token: EquationToken, boxValue: number | null, boxFinal: boolean): string {
  if (token.kind === 'number') return String(token.value);
  if (token.kind === 'operator') return token.symbol === '+' ? 'plus' : 'minus';
  if (boxValue === null) return 'box';
  // A solved step simply reads as the finished sum.
  return boxFinal ? String(boxValue) : `box with ${boxValue}`;
}

/**
 * The equation in words for a screen reader: "8 plus box equals 11".
 * With a number picked but not yet checked: "8 plus box with 3 equals 11".
 * Once the step is solved: "8 plus 3 equals 11".
 */
export function equationLabel(
  equation: Equation,
  boxValue: number | null = null,
  boxFinal = false,
): string {
  const words = (tokens: EquationToken[]) =>
    tokens.map((token) => tokenWords(token, boxValue, boxFinal)).join(' ');
  return `${words(equation.left)} equals ${words(equation.right)}`;
}

/**
 * Index, in reading order, of the token the API names as the previous step's
 * answer (`linked_token`). -1 for the first step, which has none.
 *
 * The API says exactly which token it is. That matters when the same value
 * shows twice, as in "□ − 9 = 9" after answering 9: only one of them is the link.
 */
export function linkedTokenIndex(
  equation: Equation,
  linked: LinkedToken | null | undefined,
): number {
  if (!linked) return -1;
  return linked.side === 'left' ? linked.index : equation.left.length + linked.index;
}
