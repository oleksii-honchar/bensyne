import * as fs from 'fs';
import * as yaml from 'yaml';
import { configurationSchema } from './infrastructure/config/config-schemas';

describe('live racochu.yaml validation', () => {
  it('parses ~/.config/racochu.yaml against schema', () => {
    const raw = fs.readFileSync('/Users/oleksii.honchar/.config/racochu.yaml', 'utf-8');
    const parsed = yaml.parse(raw);
    const result = configurationSchema.safeParse(parsed);
    expect(result.success).toBe(true);
    if (result.success) {
      console.log('mcp config:', JSON.stringify(result.data.mcp, null, 2));
    }
  });
});
