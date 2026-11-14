import type { Level } from '../api/puzzles';

/** The words of Today's Puzzle, in one place so the tests can quote them. */

export const LEVELS: { level: Level; label: string }[] = [
  { level: 1, label: 'Easy' },
  { level: 2, label: 'Medium' },
  { level: 3, label: 'Hard' },
];

/** What the banner says when /daily cannot be reached. The game cards still work. */
export const RESTING = 'Today’s puzzle is resting. Try a game below!';

/** The solved screen of a daily puzzle. */
export const COME_BACK = 'Come back tomorrow for a new puzzle!';
export const MORE_GAMES = 'More games';
