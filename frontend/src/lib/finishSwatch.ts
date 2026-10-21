/**
 * Representative UI swatches, not a claim about the product's exact shade.
 * For an explicitly verified manufacturer's hex value, use color.hex_code.
 */
const NAMED: Record<string, string> = {
  black: "#1d1d1f", white: "#f5f5f5", blue: "#4681bf",
  green: "#4b986d", mint: "#a3d8c1", red: "#c65059",
  pink: "#eaa2c8", purple: "#8567a9", violet: "#8466b5",
  gold: "#d5b76f", silver: "#c8cbd0", grey: "#8d939a",
  gray: "#8d939a", graphite: "#424952", orange: "#df8852",
  yellow: "#ead66e", beige: "#c9b596", cream: "#eae2ce",
  brown: "#775e50", titanium: "#a6a8a9", turquoise: "#51acac",
  lavender: "#bbaadf", midnight: "#242d48",
};

export function representativeFinishHex(name: string, verifiedHex?: string): string | null {
  if (verifiedHex && /^#[0-9a-f]{6}$/i.test(verifiedHex)) return verifiedHex;
  const tokens = name.toLowerCase().split(/[^a-z]+/).filter(Boolean);
  // Prefer unique descriptive tokens; never force a hue for a special-edition
  // marketing name that doesn't contain a recognisable colour.
  for (const token of tokens) {
    if (NAMED[token]) return NAMED[token];
  }
  return null;
}
