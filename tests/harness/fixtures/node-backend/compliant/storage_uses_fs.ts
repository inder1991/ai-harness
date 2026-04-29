import fs from 'fs';

export function loadConfig(safePath: string) {
  return fs.readFileSync(safePath).toString();
}
