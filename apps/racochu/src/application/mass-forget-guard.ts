// Mass-forget safeguard configuration.
//
// A single reconciliation run should NEVER forget more than this many files from
// a single source without an explicit override. This protects against catastrophic
// exclude patterns (e.g. `**/.*/**` that match the whole watch root) from silently
// mass-forgetting the bank.
//
// Override: set RACOCHU_RECONCILE_FORCE_FORGET=1 to bypass the guard.

export const MASS_FORGET_THRESHOLD = 20;

export const FORCE_FORGET_ENV_VAR = 'RACOCHU_RECONCILE_FORCE_FORGET';
