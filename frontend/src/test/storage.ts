import { vi } from 'vitest';

/*
 * localStorage for tests.
 *
 * Node 25 has a `localStorage` global of its own that does nothing unless Node
 * is started with a file to keep it in, and it hides the one jsdom provides.
 * setup.ts installs this in-memory one instead, fresh for every test, so the
 * tests behave the same on every Node version.
 */
class MemoryStorage implements Storage {
  private items = new Map<string, string>();

  get length(): number {
    return this.items.size;
  }

  clear(): void {
    this.items.clear();
  }

  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.items.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.items.delete(key);
  }

  setItem(key: string, value: string): void {
    this.items.set(key, String(value));
  }
}

/** Gives `window.localStorage` a new, empty, working store. */
export function installMemoryStorage(): void {
  Object.defineProperty(window, 'localStorage', {
    value: new MemoryStorage(),
    configurable: true,
    writable: true,
  });
}

/**
 * Makes every localStorage call throw, as a browser with storage blocked
 * does. Lasts until the end of the test: setup.ts installs a new store.
 */
export function blockStorage(): void {
  const blocked = () => {
    throw new DOMException('The operation is insecure.', 'SecurityError');
  };
  for (const method of ['getItem', 'setItem', 'removeItem', 'clear'] as const) {
    vi.spyOn(window.localStorage, method).mockImplementation(blocked);
  }
}
