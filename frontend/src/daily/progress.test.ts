import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { localDate } from '../api/daily';
import { blockStorage } from '../test/storage';
import { DAILY_KEY, daysPlayedThisWeek, markSolved, solvedLevels, weekOf } from './progress';

/*
 * What the device remembers about Today's Puzzle. The dates are the device's
 * local days; the week runs Monday to Sunday. 2026-03-09 is a Monday.
 */

const stored = () => JSON.parse(window.localStorage.getItem(DAILY_KEY) ?? 'null');

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  // Wednesday 11 March 2026, mid-morning.
  vi.setSystemTime(new Date(2026, 2, 11, 10, 30));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('localDate', () => {
  it('is the device calendar date, not the UTC one', () => {
    expect(localDate(new Date(2026, 2, 11, 10, 30))).toBe('2026-03-11');
    // The last minutes of a day stay on that day, whatever UTC says.
    expect(localDate(new Date(2026, 2, 11, 23, 59))).toBe('2026-03-11');
    expect(localDate(new Date(2026, 0, 1, 0, 0))).toBe('2026-01-01');
    expect(localDate()).toBe('2026-03-11');
  });
});

describe('solved levels', () => {
  it('starts empty, remembers each level once, and keeps days apart', () => {
    expect(solvedLevels('2026-03-11')).toEqual([]);

    markSolved('2026-03-11', 2);
    markSolved('2026-03-11', 2);
    markSolved('2026-03-11', 1);
    markSolved('2026-03-10', 3);

    expect(solvedLevels('2026-03-11')).toEqual([1, 2]);
    expect(solvedLevels('2026-03-10')).toEqual([3]);
    expect(stored()).toEqual({ '2026-03-10': [3], '2026-03-11': [1, 2] });
  });

  it('ignores a store it does not understand instead of crashing', () => {
    for (const junk of ['not json', '[1,2]', '{"2026-03-11": "yes"}', '{"soon": [1]}', 'null']) {
      window.localStorage.setItem(DAILY_KEY, junk);
      expect(solvedLevels('2026-03-11')).toEqual([]);
      expect(daysPlayedThisWeek()).toEqual([false, false, false, false, false, false, false]);
    }
    window.localStorage.setItem(DAILY_KEY, '{"2026-03-11": [1, 7, "2", 3, 3]}');
    expect(solvedLevels('2026-03-11')).toEqual([1, 3]);
  });

  it('plays on without storage', () => {
    blockStorage();

    expect(() => markSolved('2026-03-11', 1)).not.toThrow();
    expect(solvedLevels('2026-03-11')).toEqual([]);
    expect(daysPlayedThisWeek()).toEqual([false, false, false, false, false, false, false]);
  });
});

describe('days played this week', () => {
  it('is Monday to Sunday of the local week', () => {
    expect(weekOf(new Date(2026, 2, 11))).toEqual([
      '2026-03-09',
      '2026-03-10',
      '2026-03-11',
      '2026-03-12',
      '2026-03-13',
      '2026-03-14',
      '2026-03-15',
    ]);
    // A Sunday belongs to the week that started the Monday before it.
    expect(weekOf(new Date(2026, 2, 15))[0]).toBe('2026-03-09');
    // A Monday starts its own week.
    expect(weekOf(new Date(2026, 2, 16))[0]).toBe('2026-03-16');
    // Across a month end.
    expect(weekOf(new Date(2026, 3, 1))).toEqual([
      '2026-03-30',
      '2026-03-31',
      '2026-04-01',
      '2026-04-02',
      '2026-04-03',
      '2026-04-04',
      '2026-04-05',
    ]);
  });

  it('marks a day as played when any level was solved that day', () => {
    markSolved('2026-03-09', 1);
    markSolved('2026-03-11', 3);
    // Last week does not count; nothing carries over.
    markSolved('2026-03-08', 1);
    markSolved('2026-03-02', 2);

    expect(daysPlayedThisWeek()).toEqual([true, false, true, false, false, false, false]);
    // Seen from Sunday the 8th: that week ran from Monday the 2nd.
    expect(daysPlayedThisWeek(new Date(2026, 2, 8))).toEqual([
      true,
      false,
      false,
      false,
      false,
      false,
      true,
    ]);
  });
});
