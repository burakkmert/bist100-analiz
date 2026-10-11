// Basit form doğrulamaları
export const isEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim());
export const MIN_PASSWORD = 8;
