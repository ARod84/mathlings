import { useSyncExternalStore } from 'react';
import { isLevel, type Level } from './api/puzzles';
import { GAMES, type GameRoute } from './games/registry';

/*
 * A tiny hash router: the part of the URL after # picks the screen, and
 * changing it re-renders without reloading the page. No library.
 *
 *   #/                 home (also an empty or unknown hash)
 *   #/<game route>     one of the games in src/games/registry.ts, for
 *                      example #/pyramid or #/sum-grid
 *   #/daily/<level>    Today's Puzzle at level 1, 2 or 3 (#/daily alone is level 1)
 *   #shell-demo        the GameShell review page (dev)
 *
 * The game routes come from the registry, so a new game needs no change here.
 */

type FixedRoute = 'home' | 'shell-demo' | 'daily';

export type Route = FixedRoute | GameRoute;

const GAME_HASHES = Object.fromEntries(
  GAMES.map((game) => [game.route, `#/${game.route}`]),
) as Record<GameRoute, string>;

export const ROUTE_HASH: Record<Route, string> = {
  home: '#/',
  'shell-demo': '#shell-demo',
  daily: '#/daily',
  ...GAME_HASHES,
};

const DAILY = /^daily(?:\/([^/]*))?$/;

function cleanPath(hash: string): string {
  return hash.replace(/^#\/?/, '').replace(/\/$/, '');
}

export function parseRoute(hash: string): Route {
  const path = cleanPath(hash);
  if (path === 'shell-demo') return path;
  if (DAILY.test(path)) return 'daily';
  const game = GAMES.find((entry) => entry.route === path);
  return game ? game.route : 'home';
}

/** The address of Today's Puzzle at one level. */
export function dailyHash(level: Level): string {
  return `#/daily/${level}`;
}

/** The level in a #/daily/<level> address. Level 1 when there is none, or it is not 1, 2 or 3. */
export function parseDailyLevel(hash: string): Level {
  const level = Number(DAILY.exec(cleanPath(hash))?.[1]);
  return isLevel(level) ? level : 1;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

/** The current route, kept up to date as the hash changes. */
export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => parseRoute(window.location.hash));
}

/** The level of the Today's Puzzle address, kept up to date as the hash changes. */
export function useDailyLevel(): Level {
  return useSyncExternalStore(subscribe, () => parseDailyLevel(window.location.hash));
}

export function navigate(route: Route): void {
  window.location.hash = ROUTE_HASH[route];
}
