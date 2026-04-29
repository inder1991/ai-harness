import { execSync } from 'node:child_process';

export function listFiles() {
  return execSync('ls -la').toString();
}
