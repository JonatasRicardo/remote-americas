export const normalizeText = (value: string): string => value.trim().toLowerCase();

export const includesTerm = (haystack: string, needle: string): boolean =>
  normalizeText(haystack).includes(normalizeText(needle));
