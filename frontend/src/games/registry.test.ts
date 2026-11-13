import { describe, expect, it } from 'vitest';
import gameTopics from '../../../shared/game-topics.json';
import {
  allTopicIds,
  GAME_IDS_WITH_TOPICS,
  GAMES_WITHOUT_A_SCREEN,
  TOPIC_NAMES,
  topicsByLevel,
} from './gameTopics';
import { LEVELS, topicIdsForLevel } from './number-pyramid/pyramid';
import { GAMES } from './registry';

const TOPIC_ID = /^mt_[A-Za-z0-9_-]+$/;

describe('shared/game-topics.json', () => {
  it('has a names map and one entry per game, each with topic ids by level', () => {
    const { _names: names, ...games } = gameTopics;

    expect(Object.keys(names).length).toBeGreaterThan(0);
    for (const [id, name] of Object.entries(names)) {
      expect(id).toMatch(TOPIC_ID);
      expect(name.trim()).not.toBe('');
    }
    expect(Object.keys(games).sort()).toEqual([
      'missing-number',
      'number-pyramid',
      'sequences',
      'sum-grid',
    ]);
    for (const [gameId, entry] of Object.entries(games)) {
      expect(Object.keys(entry), gameId).toEqual(['byLevel']);
      const levels = Object.entries(entry.byLevel);
      expect(levels.length, gameId).toBeGreaterThan(0);
      for (const [level, ids] of levels) {
        expect(ids.length, `${gameId} ${level}`).toBeGreaterThan(0);
        expect(new Set(ids).size, `${gameId} ${level}`).toBe(ids.length);
        for (const id of ids) expect(id).toMatch(TOPIC_ID);
      }
    }
  });

  it('names every topic it uses, and names nothing it does not use', () => {
    const used = new Set(GAME_IDS_WITH_TOPICS.flatMap((gameId) => allTopicIds(gameId)));

    expect([...used].sort()).toEqual(Object.keys(TOPIC_NAMES).sort());
  });

  it('uses the level names each game expects', () => {
    expect(Object.keys(topicsByLevel('number-pyramid'))).toEqual(['addOnly', 'mixed', 'fourRows']);
    expect(Object.keys(topicsByLevel('missing-number'))).toEqual(['1', '2', '3']);
    expect(Object.keys(topicsByLevel('sequences'))).toEqual(['1', '2', '3']);
    expect(Object.keys(topicsByLevel('sum-grid'))).toEqual(['1', '2', '3']);
  });

  it('refuses a game it does not know', () => {
    expect(() => topicsByLevel('chess')).toThrow(/no entry for "chess"/);
  });
});

describe('games registry', () => {
  it('has an entry in the shared file for every game', () => {
    for (const game of GAMES) {
      expect(GAME_IDS_WITH_TOPICS, game.id).toContain(game.id);
      expect(game.topicIds.length, game.id).toBeGreaterThan(0);
      expect(game.topicIds).toEqual(allTopicIds(game.id));
    }
    // And the file has no game the registry lacks, except the ones that are
    // served by the backend and still waiting for a screen.
    expect([...GAME_IDS_WITH_TOPICS].sort()).toEqual(
      [...GAMES.map((game) => game.id), ...GAMES_WITHOUT_A_SCREEN].sort(),
    );
    for (const id of GAMES_WITHOUT_A_SCREEN) {
      expect(GAMES.map((game) => game.id)).not.toContain(id);
    }
  });

  it('gives each game the topics of all its levels, each once', () => {
    const byId = Object.fromEntries(GAMES.map((game) => [game.id, game.topicIds]));

    expect(byId['number-pyramid']).toEqual([
      'mt__t4afSyZRm',
      'mt_3JgrHY221M',
      'mt_ehGS_uVSJv',
      'mt_glPPG-kTQY',
    ]);
    expect(byId['missing-number']).toEqual([
      'mt_3JgrHY221M',
      'mt_oIzycTBeE4',
      'mt_XuHmIn2xje',
      'mt_ehGS_uVSJv',
    ]);
  });
});

describe('Number Pyramid topicIdsForLevel', () => {
  const ADD_ONLY = 'mt__t4afSyZRm';
  const MIXED = ['mt_3JgrHY221M', 'mt_ehGS_uVSJv'];
  const FOUR_ROWS = 'mt_glPPG-kTQY';

  it('tags each of the eight levels by its givens and its height', () => {
    expect(LEVELS.map((level) => topicIdsForLevel(level))).toEqual([
      [ADD_ONLY], // 3 rows, bottom row given
      [ADD_ONLY],
      MIXED, // 3 rows, scattered givens
      MIXED,
      [ADD_ONLY, FOUR_ROWS], // 4 rows, bottom row given
      [ADD_ONLY, FOUR_ROWS],
      [...MIXED, FOUR_ROWS], // 4 rows, scattered givens
      [...MIXED, FOUR_ROWS],
    ]);
  });

  it('follows the rule for any level, not just the listed ones', () => {
    expect(topicIdsForLevel({ rows: 3, maxBase: 99, mixed: false })).toEqual([ADD_ONLY]);
    expect(topicIdsForLevel({ rows: 2, maxBase: 5, mixed: true })).toEqual(MIXED);
    expect(topicIdsForLevel({ rows: 5, maxBase: 5, mixed: false })).toEqual([ADD_ONLY, FOUR_ROWS]);
    expect(topicIdsForLevel({ rows: 4, maxBase: 5, mixed: true })).toEqual([...MIXED, FOUR_ROWS]);
  });

  it('only uses topics the shared file names', () => {
    for (const level of LEVELS) {
      for (const id of topicIdsForLevel(level)) expect(TOPIC_NAMES[id]).toBeTruthy();
    }
  });
});
