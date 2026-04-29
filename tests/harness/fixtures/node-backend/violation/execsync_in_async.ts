import { execSync } from 'node:child_process';

export async function listFiles() {
  const result = execSync('ls -la');
  return result.toString();
}
