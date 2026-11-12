import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './design/global.css';
import { ShellDemo } from './dev/ShellDemo';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

// The demo page is mounted at the root until real games and routing exist.
createRoot(root).render(
  <StrictMode>
    <ShellDemo />
  </StrictMode>,
);
