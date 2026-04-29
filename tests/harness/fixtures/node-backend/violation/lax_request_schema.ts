import { z } from 'zod';

export const CreateUserRequest = z.object({
  name: z.string(),
  email: z.string().email(),
});
