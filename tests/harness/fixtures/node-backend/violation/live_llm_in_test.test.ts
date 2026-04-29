import OpenAI from 'openai';
import { describe, test } from 'vitest';

describe('user service', () => {
  test('summarizes', async () => {
    const client = new OpenAI();
    return client.chat.completions.create({ model: 'gpt-4', messages: [] });
  });
});
