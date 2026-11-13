import { Play } from 'lucide-react';
import { GAMES } from '../games/registry';
import { ROUTE_HASH } from '../router';
import { ForgetProgress } from './ForgetProgress';
import styles from './Home.module.css';

/** The home screen: one card per game in the registry. */
export function Home() {
  return (
    <div className={styles.home}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mathlings</h1>
        <p className={styles.tagline}>Pick a game and start puzzling.</p>
      </header>

      <ul className={styles.games} aria-label="Games">
        {GAMES.map((game) => (
          <li key={game.id} className={styles.card} data-house={game.house}>
            <h2 className={styles.cardTitle}>{game.title}</h2>
            <p className={styles.description}>{game.description}</p>
            <a
              className={styles.play}
              href={ROUTE_HASH[game.route]}
              aria-label={`Play ${game.title}`}
            >
              <Play aria-hidden="true" size={20} strokeWidth={3} fill="currentColor" />
              <span>Play</span>
            </a>
          </li>
        ))}
      </ul>

      <footer className={styles.footer}>
        <ForgetProgress />
      </footer>
    </div>
  );
}
