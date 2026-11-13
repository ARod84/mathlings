import type { HouseKey } from '../design/tokens';
import type { Route } from '../router';

/*
 * Every game the home screen offers. To add a game: add an entry here, a
 * route in router.ts, a folder under src/games with the component and its
 * tests, and a line in App.tsx that renders it for the route.
 */

export interface GameEntry {
  id: string;
  title: string;
  route: Exclude<Route, 'home' | 'shell-demo'>;
  /** Accent color of the game's card and of its GameShell. */
  house: HouseKey;
  /** One line for the home screen. */
  description: string;
}

export const GAMES: readonly GameEntry[] = [
  {
    id: 'number-pyramid',
    title: 'Number Pyramid',
    route: 'pyramid',
    house: 'builders',
    description: 'Every block is the sum of the two below it. Fill in the gaps.',
  },
  {
    id: 'missing-number',
    title: 'Missing Number Chains',
    route: 'missing-number',
    house: 'navigators',
    description: 'Find the missing number, then use it to crack the next one.',
  },
];

export function gameFor(route: GameEntry['route']): GameEntry {
  const game = GAMES.find((entry) => entry.route === route);
  if (!game) throw new Error(`No game registered for route ${route}`);
  return game;
}
