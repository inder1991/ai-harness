import { logger } from '@/lib/log';

export function handle(id: string) {
  logger.info({ userId: id }, 'user fetched');
}
