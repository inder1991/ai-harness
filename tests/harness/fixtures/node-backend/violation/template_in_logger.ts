import { logger } from '@/lib/log';

export function handle(id: string) {
  logger.info(`user ${id} fetched`);
}
