// Cam görünümlü metin girişi; ikon, hata mesajı ve şifre göster/gizle desteği.
import { Ionicons } from '@expo/vector-icons';
import { forwardRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { font, radius } from '@/theme/colors';
import { useTheme } from '@/theme/ThemeProvider';
import { AppText } from './AppText';
import type { IconName } from './GlassIcon';

interface Props extends TextInputProps {
  label?: string;
  icon?: IconName;
  error?: string | null;
  /** true ise göz ikonu ile şifre göster/gizle */
  password?: boolean;
}

export const TextField = forwardRef<TextInput, Props>(function TextField(
  { label, icon, error, password, style, onFocus, onBlur, ...rest },
  ref,
) {
  const p = useTheme();
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);

  const borderColor = error ? p.down : focused ? p.accent : p.glassBorder;

  return (
    <View style={styles.wrap}>
      {label ? (
        <AppText variant="caption" color="textMuted" style={styles.label}>
          {label}
        </AppText>
      ) : null}
      <View style={[styles.field, { backgroundColor: p.inputFill, borderColor }]}>
        {icon ? <Ionicons name={icon} size={18} color={focused ? p.accent : p.textFaint} /> : null}
        <TextInput
          ref={ref}
          placeholderTextColor={p.textFaint}
          selectionColor={p.accent}
          secureTextEntry={password ? hidden : rest.secureTextEntry}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          style={[styles.input, { color: p.text }, style]}
          {...rest}
        />
        {password ? (
          <Pressable
            hitSlop={10}
            onPress={() => setHidden((h) => !h)}
            accessibilityLabel={hidden ? 'Şifreyi göster' : 'Şifreyi gizle'}
          >
            <Ionicons name={hidden ? 'eye-outline' : 'eye-off-outline'} size={19} color={p.textFaint} />
          </Pressable>
        ) : null}
      </View>
      {error ? (
        <AppText variant="caption" color="down" style={styles.error}>
          {error}
        </AppText>
      ) : null}
    </View>
  );
});

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  label: { marginLeft: 4 },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 52,
    paddingHorizontal: 16,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  input: { flex: 1, fontFamily: font.regular, fontSize: 15, paddingVertical: 12 },
  error: { marginLeft: 4 },
});
