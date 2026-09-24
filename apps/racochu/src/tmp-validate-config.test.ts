import * as fs from 'fs';
import * as os from 'os';
import * as yaml from 'yaml';
import { configurationSchema } from './infrastructure/config/config-schemas';

describe('live racochu.yaml validation', () => {
  it('parses ~/.config/racochu.yaml against schema', () => {
    const homeDir = os.homedir();
    const configPath = `${homeDir}/.config/racochu.yaml`;
    const raw = fs.readFileSync(configPath, 'utf-8');
    const parsed = yaml.parse(raw);
    const result = configurationSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      console.log('mcp config:', JSON.stringify(result.data.mcp, null, 2));
    }
  });
});
