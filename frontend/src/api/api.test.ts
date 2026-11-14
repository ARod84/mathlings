// @vitest-environment node
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';
import { describe, expect, it } from 'vitest';

const OPENAPI_JSON = new URL('../../../openapi.json', import.meta.url);
const SCHEMA_FILE = new URL('./schema.d.ts', import.meta.url);

/** What `npm run api:types` would write, minus the header comment it adds. */
function withoutHeader(source: string): string {
  return source.replace(/^\/\*\*[\s\S]*?\*\/\s*/, '').trim();
}

describe('generated API types', () => {
  it('schema.d.ts is up to date with the repo-root openapi.json', async () => {
    const generated = astToString(await openapiTS(OPENAPI_JSON));
    const committed = readFileSync(fileURLToPath(SCHEMA_FILE), 'utf8');

    expect(withoutHeader(committed), 'src/api/schema.d.ts is stale. Run: npm run api:types').toBe(
      withoutHeader(generated),
    );
  });

  it('describes the puzzle routes the game uses', () => {
    const committed = readFileSync(fileURLToPath(SCHEMA_FILE), 'utf8');

    for (const path of [
      '"/api/v1/puzzles/missing-number"',
      '"/api/v1/puzzles/{puzzle_id}"',
      '"/api/v1/puzzles/{puzzle_id}/steps/{index}/check"',
      '"/api/v1/puzzles/{puzzle_id}/steps/{index}/hints/{tier}"',
      '"/api/v1/daily"',
    ]) {
      expect(committed).toContain(path);
    }
  });
});
