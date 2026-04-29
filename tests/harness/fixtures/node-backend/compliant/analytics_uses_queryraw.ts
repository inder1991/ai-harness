import { prisma } from './client';

export async function findRecent(days: number) {
  return prisma.$queryRaw`SELECT * FROM events WHERE created_at > NOW() - INTERVAL '${days} days'`;
}
