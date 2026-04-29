import { describe, test } from 'vitest';

describe('api', () => {
  test('lists users', async () => {
    const r = await fetch('/api/users');
    return r.json();
  });
});
