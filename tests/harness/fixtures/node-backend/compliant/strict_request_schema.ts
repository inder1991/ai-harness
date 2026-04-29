import { z } from 'zod';

export const CreateUserRequest = z.object({
  name: z.string(),
  email: z.string().email(),
}).strict();

export const UserResponse = z.object({
  id: z.string(),
  name: z.string(),
}).readonly();
