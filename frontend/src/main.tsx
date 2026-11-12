import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './design/global.css';
import { ShellDemo } from './dev/ShellDemo';
import { NumberPyramid } from './games/number-pyramid/NumberPyramid';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

// No routing yet: the game is the app, and the shell review page sits behind #shell-demo.
const showShellDemo = window.location.hash === '#shell-demo';
window.addEventListener('hashchange', () => window.location.reload());

createRoot(root).render(
  <StrictMode>
    {showShellDemo ? (
      <ShellDemo />
    ) : (
      <main style={{ minHeight: '100dvh', padding: 'var(--space-4)' }}>
        <NumberPyramid seed={Date.now()} />
      </main>
    )}
  </StrictMode>,
);
