// Tema rengini ve yazı stilini otomatik uygulayan metin bileşeni.
import { Text, type TextProps } from 'react-native';

import { type } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';

type Variant = keyof typeof type;
type Color = 'text' | 'textMuted' | 'textFaint' | 'accent' | 'up' | 'down' | 'warn' | 'onAccent';

interface Props extends TextProps {
  variant?: Variant;
  color?: Color;
}

export function AppText({ variant = 'body', color = 'text', style, ...rest }: Props) {
  const p = useTheme();
  return <Text {...rest} style={[type[variant], { color: p[color] }, style]} />;
}
