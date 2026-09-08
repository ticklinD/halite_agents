/**
 * Halite theme — Hermes-inspired dark palette (gold/bronze on near-black).
 * Mirrors the Hermes default skin: #101014 bg, #CD7F32 border, #FFD700 primary,
 * #FFBF00 accent, #FFF8DC text.
 */
export const theme = {
  bg: '#101014',
  surface: '#1a1a2e',
  primary: '#FFD700',
  accent: '#FFBF00',
  border: '#CD7F32',
  text: '#FFF8DC',
  muted: '#9a9a9a',
  label: '#e0c080',
  ok: '#8FBC8F',
  error: '#ef5350',
  warn: '#ffa726',
  prompt: '#FFF8DC',
  tool: '#FFBF00',
  thinking: '#b0a090',
  sessionLabel: '#e0c080',
  sessionBorder: '#CD7F32',
  shellDollar: '#4dabf7'
} as const

export type HaliteTheme = typeof theme

// ── ASCII banner (ANSI-shadow block letters: HALITE) ─────────────────
// 6 rows, 65 cols wide. Rendered with a gold→bronze vertical gradient
// exactly like Hermes' LOGO_ART gradient.
const LOGO_ART = [
  '██╗  ██╗ █████╗ ██╗     ██╗████████╗███████╗',
  '██║  ██║██╔══██╗██║     ██║╚══██╔══╝██╔════╝',
  '███████║███████║██║     ██║   ██║   █████╗  ',
  '██╔══██║██╔══██║██║     ██║   ██║   ██╔══╝  ',
  '██║  ██║██║  ██║███████╗██║   ██║   ███████╗',
  '╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝   ╚═╝   ╚══════╝'
] as const

const LOGO_GRADIENT = [0, 0, 1, 1, 2, 2] as const
const GRADIENT = [theme.primary, theme.accent, theme.border, theme.muted] as const

export const LOGO_WIDTH = Math.max(...LOGO_ART.map(line => line.length))

export type LogoLine = [string, string]

export function logo(): LogoLine[] {
  return LOGO_ART.map((text, i) => [GRADIENT[LOGO_GRADIENT[i] ?? theme.muted]!, text])
}

export function artWidth(lines: LogoLine[]): number {
  return lines.reduce((m, [, t]) => Math.max(m, t.length), 0)
}