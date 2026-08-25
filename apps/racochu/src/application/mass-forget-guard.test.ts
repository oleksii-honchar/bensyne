import { FORCE_FORGET_ENV_VAR, MASS_FORGET_THRESHOLD } from './mass-forget-guard';

describe('mass-forget-guard constants', () => {
  it('keeps the mass-forget threshold at 20', () => {
    expect(MASS_FORGET_THRESHOLD).toBe(20);
  });

  it('keeps the force-forget override env var name stable', () => {
    expect(FORCE_FORGET_ENV_VAR).toBe('RACOCHU_RECONCILE_FORCE_FORGET');
  });
});
