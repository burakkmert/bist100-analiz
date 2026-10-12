// expo-env.d.ts .gitignore'da ve yalnızca `expo start` ile üretiliyor; CI'da (npx tsc) yok.
// Expo'nun ortam tiplerini (process.env.EXPO_PUBLIC_*, görsel importları) her yerde açık tutar.
/// <reference types="expo/types" />
