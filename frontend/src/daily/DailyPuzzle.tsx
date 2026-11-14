import { useEffect, useState } from 'react';
import { getDailyPuzzle, localDate, type DailyGame, type DailyPuzzle as Daily } from '../api/daily';
import type { ApiResult, GameId, Level, PuzzleOf } from '../api/puzzles';
import { MissingNumber } from '../games/missing-number/MissingNumber';
import { GAMES } from '../games/registry';
import { Sequences } from '../games/sequences/Sequences';
import { LoadingScreen, ProblemScreen } from '../games/session/SessionScreens';
import { SumGrid } from '../games/sum-grid/SumGrid';
import type { SessionTiming, SinglePuzzle } from '../games/usePuzzleSession';
import { GameShell } from '../shell';
import { COME_BACK, MORE_GAMES } from './copy';
import { markSolved } from './progress';

/*
 * The #/daily/<level> screen: Today's Puzzle, played as one puzzle in the
 * day's game. It fetches /daily for the device's local date, then hands the
 * puzzle to the game's own component in its single-puzzle mode (see
 * SinglePuzzle in games/usePuzzleSession.ts), so the game looks and behaves
 * as it always does, except that there is no round and no start screen, every
 * check says `context: "daily"`, and the solved screen says to come back
 * tomorrow. The solve is remembered on this device only (progress.ts).
 */

export interface DailyPuzzleProps {
  level: Level;
  /** Back to the home screen; also what "More games" does. */
  onExit: () => void;
  /** How long the pauses between steps last. Tests shorten them. */
  timing?: SessionTiming;
}

type Loaded = { status: 'loading' } | { status: 'error' } | { status: 'ready'; daily: Daily };

/** The registry entry of the day's game, for its house color. */
function houseOf(game: DailyGame) {
  return GAMES.find((entry) => entry.id === game)?.house ?? 'navigators';
}

export function DailyPuzzle({ level, onExit, timing }: DailyPuzzleProps) {
  // The device's day, read once when the screen opens.
  const [date] = useState(() => localDate());
  const [loaded, setLoaded] = useState<Loaded>({ status: 'loading' });
  // Bumped by "Try again".
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getDailyPuzzle(date, level, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setLoaded(
        result.status === 'ok' ? { status: 'ready', daily: result.data } : { status: 'error' },
      );
    });
    return () => controller.abort();
  }, [date, level, attempt]);

  if (loaded.status !== 'ready') {
    return (
      <GameShell
        title="Today’s Puzzle"
        instruction={
          loaded.status === 'loading' ? 'Getting today’s puzzle ready…' : 'Let’s try that again'
        }
        house="navigators"
        progress={{ current: 0, total: 1 }}
        feedback="idle"
        onExit={onExit}
      >
        {loaded.status === 'loading' ? (
          <LoadingScreen />
        ) : (
          <ProblemScreen
            onRetry={() => {
              setLoaded({ status: 'loading' });
              setAttempt((count) => count + 1);
            }}
          />
        )}
      </GameShell>
    );
  }

  const { puzzle } = loaded.daily;

  /** The single-puzzle description for the day's game, once its shape is known. */
  function single<G extends GameId>(game: G, known: PuzzleOf<G>): SinglePuzzle<G, Level> {
    return {
      puzzle: known,
      level,
      context: 'daily',
      reload: async (signal): Promise<ApiResult<PuzzleOf<G>>> => {
        const result = await getDailyPuzzle(date, level, signal);
        if (result.status !== 'ok') return result;
        // Today's game cannot change within the day; if it somehow did, this is not the puzzle asked for.
        if (result.data.puzzle.game !== game) return { status: 'notFound' };
        return { status: 'ok', data: result.data.puzzle as PuzzleOf<G> };
      },
      onSolved: () => markSolved(date, level),
      solved: { message: COME_BACK, nextLabel: MORE_GAMES, onNext: onExit },
    };
  }

  const house = houseOf(puzzle.game);
  switch (puzzle.game) {
    case 'missing-number':
      return (
        <MissingNumber
          house={house}
          onExit={onExit}
          timing={timing}
          single={single('missing-number', puzzle)}
        />
      );
    case 'sequences':
      return (
        <Sequences
          house={house}
          onExit={onExit}
          timing={timing}
          single={single('sequences', puzzle)}
        />
      );
    case 'sum-grid':
      return (
        <SumGrid
          house={house}
          onExit={onExit}
          timing={timing}
          single={single('sum-grid', puzzle)}
        />
      );
  }
}
