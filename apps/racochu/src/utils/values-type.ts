/**
 * Utility type to extract values from an enum or const union.
 */

export type ValuesType<T> = T[keyof T];
