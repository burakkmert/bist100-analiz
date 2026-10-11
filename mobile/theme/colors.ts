import type { TextStyle } from 'react-native';

// Tasarım belirteçleri (design tokens). Tüm renkler buradan gelir; ekranlarda sabit renk yazılmaz.

export type ThemeName = 'light' | 'dark';

export interface Palette {
  name: ThemeName;
  /** Arka plan gradyanı: üstten alta */
  bgGradient: readonly [string, string, ...string[]];
  /** Arka planda dönen ikinci gradyan (renk yönünü değiştirir) */
  bgSweep: readonly [string, string, ...string[]];
  /** En üstte ince örtü: okunurluk için */
  bgVeil: string;
  /** Arka planda akan ışık lekeleri: [renk, opaklık] */
  blobs: readonly { color: string; opacity: number }[];

  text: string;
  textMuted: string;
  textFaint: string;

  /** Cam yüzeyler */
  glassTint: 'light' | 'dark';
  glassFill: string;
  glassFillStrong: string;
  glassBorder: string;
  glassHighlight: string; // üst kenardaki parlama
  glassShadow: string;

  accent: string;
  accentSoft: string;
  onAccent: string;

  up: string;
  down: string;
  flat: string;
  warn: string;

  inputFill: string;
  separator: string;
}

export const dark: Palette = {
  name: 'dark',
  // Koyu lacivertten koyu griye
  bgGradient: ['#0A1838', '#0F1C35', '#161B26', '#1B1D22'],
  bgSweep: ['rgba(20,45,110,0.9)', 'rgba(10,24,56,0)', 'rgba(40,44,52,0.9)'],
  bgVeil: 'rgba(8,14,30,0.18)',
  blobs: [
    { color: '#2F5BEA', opacity: 0.7 }, // kraliyet mavisi
    { color: '#0E9AB5', opacity: 0.5 }, // camgöbeği
    { color: '#6A3FE0', opacity: 0.5 }, // menekşe
    { color: '#1B2E6B', opacity: 0.85 }, // derin lacivert
    { color: '#3E4A5E', opacity: 0.6 }, // dumanlı gri
  ],

  text: '#F1F4FA',
  textMuted: 'rgba(225,232,245,0.68)',
  textFaint: 'rgba(225,232,245,0.42)',

  glassTint: 'dark',
  glassFill: 'rgba(255,255,255,0.06)',
  glassFillStrong: 'rgba(255,255,255,0.11)',
  glassBorder: 'rgba(255,255,255,0.14)',
  glassHighlight: 'rgba(255,255,255,0.22)',
  glassShadow: '#000000',

  accent: '#6EA8FF',
  accentSoft: 'rgba(110,168,255,0.18)',
  onAccent: '#06122B',

  up: '#3DDC97',
  down: '#FF6B6B',
  flat: '#A7B1C2',
  warn: '#FFC857',

  inputFill: 'rgba(255,255,255,0.07)',
  separator: 'rgba(255,255,255,0.09)',
};

export const light: Palette = {
  name: 'light',
  // Pastel "mesh" gradyan (referans görsel): sol üst mavi, sağ üst orkide, orta nane yeşili,
  // sol alt açık gri, sağ alt çelik mavisi. Lekeler AnimatedBackground'daki yörüngelerde akar;
  // sıra ORBITS ile eşleşir: [sol üst, sağ üst, sol alt, sağ alt, orta].
  bgGradient: ['#6B8DD3', '#8AA3C4', '#86ACB4', '#7E9CBF'],
  bgSweep: ['rgba(182,116,200,0.55)', 'rgba(134,172,180,0)', 'rgba(197,201,206,0.6)'],
  bgVeil: 'rgba(255,255,255,0.10)',
  blobs: [
    { color: '#5A84D6', opacity: 0.95 }, // mavi (sol üst)
    { color: '#B872C9', opacity: 0.9 }, // orkide / pembe-mor (sağ üst)
    { color: '#C7CBD0', opacity: 0.95 }, // açık gri (sol alt)
    { color: '#5B7FB0', opacity: 0.9 }, // çelik mavisi (sağ alt)
    { color: '#7DC4A4', opacity: 0.95 }, // nane yeşili (orta)
  ],

  text: '#0E1526',
  textMuted: 'rgba(14,21,38,0.62)',
  textFaint: 'rgba(14,21,38,0.38)',

  glassTint: 'light',
  glassFill: 'rgba(255,255,255,0.55)',
  glassFillStrong: 'rgba(255,255,255,0.78)',
  glassBorder: 'rgba(255,255,255,0.95)',
  glassHighlight: 'rgba(255,255,255,1)',
  glassShadow: '#8A93A3',

  accent: '#2F6FED',
  accentSoft: 'rgba(47,111,237,0.12)',
  onAccent: '#FFFFFF',

  up: '#12A36B',
  down: '#E03E3E',
  flat: '#6B7385',
  warn: '#C98A00',

  inputFill: 'rgba(255,255,255,0.6)',
  separator: 'rgba(14,21,38,0.08)',
};

export const radius = { sm: 10, md: 16, lg: 22, xl: 28, pill: 999 } as const;
export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const font = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
} as const;

export const type = {
  display: { fontFamily: font.bold, fontSize: 32, letterSpacing: -0.8 },
  title: { fontFamily: font.semibold, fontSize: 22, letterSpacing: -0.4 },
  heading: { fontFamily: font.semibold, fontSize: 17, letterSpacing: -0.2 },
  body: { fontFamily: font.regular, fontSize: 15, lineHeight: 21 },
  bodyMedium: { fontFamily: font.medium, fontSize: 15, lineHeight: 21 },
  caption: { fontFamily: font.medium, fontSize: 12.5, letterSpacing: 0.1 },
  // Fiyatlar için sabit genişlikli rakamlar
  number: { fontFamily: font.semibold, fontVariant: ['tabular-nums'] },
} satisfies Record<string, TextStyle>;
