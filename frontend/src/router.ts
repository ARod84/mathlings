import { useSyncExternalStore } from 'react';
import { GAMES, type GameRoute } from './games/registry';

/*
 * A tiny hash router: the part of the URL after # picks the screen, and
 * changing it re-renders without reloading the page. No library.
 *
 *   #/                 home (also an empty or unknown hash)
 *   #/<game route>     one of the games in src/games/registry.ts, for
 *                      example #/pyramid or #/sum-grid
 *   #shell-demo        the GameShell review page (dev)
 *
 * The game routes come from the registry, so a new game needs no change here.
 */

type FixedRoute = 'home' | 'shell-demo';

export type Route = FixedRoute | GameRoute;

const GAME_HASHES = Object.fromEntries(
  GAMES.map((game) => [game.route, `#/${game.route}`]),
) as Record<GameRoute, string>;

export const ROUTE_HASH: Record<Route, string> = {
  home: '#/',
  'shell-demo': '#shell-demo',
  ...GAME_HASHES,
};

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '').replace(/\/$/, '');
  if (path === 'shell-demo') return path;
  const game = GAMES.find((entry) => entry.route === path);
  return game ? game.route : 'home';
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

/** The current route, kept up to date as the hash changes. */
export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => parseRoute(window.location.hash));
}

export function navigate(route: Route): void {
  window.location.hash = ROUTE_HASH[route];
}
