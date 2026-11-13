import { useSyncExternalStore } from 'react';

/*
 * A tiny hash router: the part of the URL after # picks the screen, and
 * changing it re-renders without reloading the page. No library.
 *
 *   #/                 home (also an empty or unknown hash)
 *   #/pyramid          Number Pyramid
 *   #/missing-number   Missing Number Chains
 *   #/sequences        Next in Line
 *   #shell-demo        the GameShell review page (dev)
 */

export type Route = 'home' | 'pyramid' | 'missing-number' | 'sequences' | 'shell-demo';

export const ROUTE_HASH: Record<Route, string> = {
  home: '#/',
  pyramid: '#/pyramid',
  'missing-number': '#/missing-number',
  sequences: '#/sequences',
  'shell-demo': '#shell-demo',
};

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#\/?/, '').replace(/\/$/, '');
  if (
    path === 'pyramid' ||
    path === 'missing-number' ||
    path === 'sequences' ||
    path === 'shell-demo'
  ) {
    return path;
  }
  return 'home';
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
