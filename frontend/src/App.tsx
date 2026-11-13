import { useState } from 'react';
import { ShellDemo } from './dev/ShellDemo';
import { MissingNumber } from './games/missing-number/MissingNumber';
import { NumberPyramid } from './games/number-pyramid/NumberPyramid';
import { gameFor } from './games/registry';
import { Home } from './home/Home';
import { navigate, useRoute } from './router';

const goHome = () => navigate('home');

/** Picks the screen for the current route. See router.ts for the routes. */
export function App() {
  const route = useRoute();
  // One seed per visit to the app: Number Pyramid's puzzles differ between
  // page loads but stay put while the child moves between screens.
  const [seed] = useState(() => Date.now());

  if (route === 'shell-demo') return <ShellDemo />;

  return (
    <main style={{ minHeight: '100dvh', padding: 'var(--space-4)' }}>
      {route === 'home' && <Home />}
      {route === 'pyramid' && (
        <NumberPyramid seed={seed} house={gameFor('pyramid').house} onExit={goHome} />
      )}
      {route === 'missing-number' && (
        <MissingNumber house={gameFor('missing-number').house} onExit={goHome} />
      )}
    </main>
  );
}
