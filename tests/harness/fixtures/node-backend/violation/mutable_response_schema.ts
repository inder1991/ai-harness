import { z } from 'zod';

export const UserResponse = z.object({
  id: z.string(),
  name: z.string(),
});
