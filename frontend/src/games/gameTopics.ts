import gameTopics from '../../../shared/game-topics.json';

/*
 * The taxonomy topics each game practises, read from the repo-root
 * shared/game-topics.json, the one file both apps use. Nothing here is shown
 * to a child; it is there for the adaptive work to come.
 */

/** Topic ids per level name, for one game. */
export type TopicsByLevel = Readonly<Record<string, readonly string[]>>;

export const TOPIC_NAMES: Readonly<Record<string, string>> = gameTopics._names;

const BY_GAME: Readonly<Record<string, { byLevel: TopicsByLevel }>> = {
  'number-pyramid': gameTopics['number-pyramid'],
  'missing-number': gameTopics['missing-number'],
  sequences: gameTopics.sequences,
};

/**
 * Games the backend already has puzzles for (and so topics in the shared
 * file) that have no screen here yet. Empty once each has an entry in
 * registry.ts.
 */
export const GAMES_WITHOUT_A_SCREEN: readonly string[] = [];

/** Ids of the games that have an entry in the shared file. */
export const GAME_IDS_WITH_TOPICS: readonly string[] = Object.keys(BY_GAME);

export function topicsByLevel(gameId: string): TopicsByLevel {
  const entry = BY_GAME[gameId];
  if (!entry) throw new Error(`shared/game-topics.json has no entry for "${gameId}"`);
  return entry.byLevel;
}

/** Every topic a game touches at any level, each once, in the order the file lists them. */
export function allTopicIds(gameId: string): string[] {
  return [...new Set(Object.values(topicsByLevel(gameId)).flat())];
}
