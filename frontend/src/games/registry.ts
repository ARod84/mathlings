import type { HouseKey } from '../design/tokens';
import { allTopicIds } from './gameTopics';

/*
 * Every game the home screen offers. To add a game: add an entry here, its
 * topics in the repo-root shared/game-topics.json, a folder under src/games
 * with the component and its tests, and a line in App.tsx that renders it
 * for its route. The router builds its routes from this list: an entry's
 * `route` becomes the hash `#/<route>`, with nothing to edit in router.ts.
 */

interface GameDefinition {
  id: string;
  title: string;
  /** The part of the hash after `#/`. Lower-case letters and hyphens. */
  route: string;
  /** Accent color of the game's card and of its GameShell. */
  house: HouseKey;
  /** One line for the home screen. */
  description: string;
  /**
   * Taxonomy topics the game practises, across all its levels, from
   * shared/game-topics.json. Not shown anywhere; for the adaptive work to come.
   */
  topicIds: readonly string[];
}

export const GAMES = [
  {
    id: 'number-pyramid',
    title: 'Number Pyramid',
    route: 'pyramid',
    house: 'builders',
    description: 'Every block is the sum of the two below it. Fill in the gaps.',
    topicIds: allTopicIds('number-pyramid'),
  },
  {
    id: 'missing-number',
    title: 'Missing Number Chains',
    route: 'missing-number',
    house: 'navigators',
    description: 'Find the missing number, then use it to crack the next one.',
    topicIds: allTopicIds('missing-number'),
  },
  {
    id: 'sequences',
    title: 'Next in Line',
    route: 'sequences',
    house: 'scientists',
    description: 'Find the missing number in the pattern.',
    topicIds: allTopicIds('sequences'),
  },
  {
    id: 'sum-grid',
    title: 'Sum Grid',
    route: 'sum-grid',
    house: 'artisans',
    description: 'Fill the grid so every row and column adds up.',
    topicIds: allTopicIds('sum-grid'),
  },
] as const satisfies readonly GameDefinition[];

export type GameEntry = (typeof GAMES)[number];
/** The route of one of the games, as a literal type: 'pyramid' | 'missing-number' | ... */
export type GameRoute = GameEntry['route'];

export function gameFor(route: GameRoute): GameEntry {
  const game = GAMES.find((entry) => entry.route === route);
  if (!game) throw new Error(`No game registered for route ${route}`);
  return game;
}
