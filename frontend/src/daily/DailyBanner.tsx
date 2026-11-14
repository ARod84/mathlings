import { Check } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getDailyPuzzle, localDate, type DailyGame } from '../api/daily';
import { getNextPuzzle } from '../api/player';
import { isLevel, type Level } from '../api/puzzles';
import { GAMES } from '../games/registry';
import { dailyHash } from '../router';
import { LEVELS, RESTING } from './copy';
import styles from './DailyBanner.module.css';
import { daysPlayedThisWeek, solvedLevels } from './progress';

/*
 * The "Today's Puzzle" banner on the home screen: the game of the day and
 * three ways in, Easy, Medium and Hard. Everyone gets the same puzzle on the
 * same day, so the date sent is the device's local day (see api/daily.ts).
 *
 * What it remembers lives on this device only (progress.ts): a check mark on
 * each level solved today, and "Days played this week". There is NO STREAK,
 * on purpose; the note in progress.ts says why. Please do not add one.
 */

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

type Today = { status: 'loading' } | { status: 'ready'; game: DailyGame } | { status: 'resting' };

/** The game's name as the home screen shows it, from the registry. */
function titleOf(game: DailyGame): string {
  return GAMES.find((entry) => entry.id === game)?.title ?? game;
}

/** Seven dots, Monday to Sunday, filled for each day Today's Puzzle was played. */
function WeekDots({ played }: { played: boolean[] }) {
  const count = played.filter(Boolean).length;
  const names = WEEKDAYS.filter((_, index) => played[index]);
  const spoken =
    count === 0 ? 'none yet' : `${count} of 7${names.length ? `: ${names.join(', ')}` : ''}`;
  return (
    <p className={styles.week}>
      <span>Days played this week:</span>{' '}
      <span className={styles.dots} role="img" aria-label={spoken} data-testid="week-dots">
        {played.map((filled, index) => (
          <span key={index} data-played={filled || undefined}>
            {filled ? '●' : '○'}
          </span>
        ))}
      </span>
    </p>
  );
}

export function DailyBanner() {
  // The device's day, read once: the banner lives for one visit to the home screen.
  const [date] = useState(() => localDate());
  const [today, setToday] = useState<Today>({ status: 'loading' });
  const [suggested, setSuggested] = useState<Level | null>(null);
  const solved = solvedLevels(date);
  const played = daysPlayedThisWeek();

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      // Level 1 is as good as any for learning the game of the day.
      const result = await getDailyPuzzle(date, 1, controller.signal);
      if (controller.signal.aborted) return;
      if (result.status !== 'ok') {
        setToday({ status: 'resting' });
        return;
      }
      const game = result.data.puzzle.game;
      setToday({ status: 'ready', game });
      // What the backend would have this player do in that game, if it can say.
      const next = await getNextPuzzle(game, controller.signal);
      if (controller.signal.aborted) return;
      if (next !== null && isLevel(next.level)) setSuggested(next.level);
    };
    void load();
    return () => controller.abort();
  }, [date]);

  return (
    <section className={styles.banner} aria-label="Today’s Puzzle" data-status={today.status}>
      <div className={styles.heading}>
        <p className={styles.kicker}>Today’s Puzzle</p>
        <h2 className={styles.title}>
          {today.status === 'ready' ? titleOf(today.game) : today.status === 'loading' ? '…' : ''}
        </h2>
        <p className={styles.blurb}>
          {today.status === 'resting'
            ? RESTING
            : 'The same puzzle for everyone today. Pick how tricky.'}
        </p>
      </div>

      {today.status === 'ready' && (
        <div className={styles.levels} role="group" aria-label="Today’s Puzzle levels">
          {LEVELS.map(({ level, label }) => {
            const done = solved.includes(level);
            const hinted = suggested === level;
            return (
              <a
                key={level}
                className={styles.level}
                href={dailyHash(level)}
                data-level={level}
                data-solved={done || undefined}
                data-suggested={hinted || undefined}
                aria-label={`${label}${done ? ', solved' : ''}${hinted ? ', suggested' : ''}`}
              >
                <span className={styles.levelLabel}>
                  {done && <Check aria-hidden="true" size={20} strokeWidth={3.5} />}
                  <span>{label}</span>
                </span>
                {hinted && (
                  <span className={styles.suggested} aria-hidden="true">
                    suggested
                  </span>
                )}
              </a>
            );
          })}
        </div>
      )}

      <WeekDots played={played} />
    </section>
  );
}
