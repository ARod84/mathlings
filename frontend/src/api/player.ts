import { api } from './client';

/*
 * The anonymous player id.
 *
 * It is a random UUID (version 4) that this browser makes on first use and
 * keeps in localStorage. The backend stores practice history under it: which
 * steps were tried, which answers were given, which hints were fetched.
 *
 * PRIVACY. The id is a pseudonymous identifier, NOT authentication. It says
 * nothing about who the child is, and anyone who has it can read or delete
 * its history, which is acceptable only because that history is anonymous
 * practice data. Never send a name, an email or anything else personal with
 * it, and do not put it in a cookie or a URL.
 *
 * If storage is unavailable (private mode, blocked storage) there is no id:
 * the game plays as usual and the backend stores nothing.
 */

export const PLAYER_ID_KEY = 'mathlings.playerId';
export const PLAYER_ID_HEADER = 'X-Player-Id';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** The id already on this device, or null. Never creates one. */
function storedPlayerId(): string | null {
  try {
    const stored = window.localStorage.getItem(PLAYER_ID_KEY);
    return stored !== null && UUID_V4.test(stored) ? stored : null;
  } catch {
    return null;
  }
}

/**
 * The id for this device, made on first call. Null when it cannot be kept,
 * in which case nothing is sent and nothing is stored.
 */
export function getPlayerId(): string | null {
  const stored = storedPlayerId();
  if (stored !== null) return stored;
  try {
    // Also replaces a value that is not a UUID, which the backend would reject.
    const fresh = globalThis.crypto.randomUUID();
    window.localStorage.setItem(PLAYER_ID_KEY, fresh);
    return fresh;
  } catch {
    return null;
  }
}

export type ForgetResult = 'forgotten' | 'failed';

/**
 * Deletes this device's history on the server, then forgets the id. The next
 * play makes a new one.
 *
 * If the server cannot be reached the id is kept, so the child (or a parent)
 * can try again: dropping it first would leave history nobody can delete.
 */
export async function forgetPlayer(): Promise<ForgetResult> {
  const id = storedPlayerId();
  if (id !== null) {
    try {
      const { response } = await api.DELETE('/api/v1/players/me', {
        params: { header: { [PLAYER_ID_HEADER]: id } },
      });
      if (!response.ok) return 'failed';
    } catch {
      return 'failed';
    }
  }
  try {
    window.localStorage.removeItem(PLAYER_ID_KEY);
  } catch {
    // Storage is blocked, so there was no id to keep in the first place.
  }
  return 'forgotten';
}
