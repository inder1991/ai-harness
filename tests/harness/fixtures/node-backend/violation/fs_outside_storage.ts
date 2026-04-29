import fs from 'fs';

export function loadConfig() {
  const raw = fs.readFileSync('/etc/app.conf');
  return raw.toString();
}
