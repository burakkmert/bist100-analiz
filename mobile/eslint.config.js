// ESLint (flat config) — Expo'nun önerdiği kurallar. Çalıştırma: npm run lint
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    // Yanlışlıkla iç içe kopyalanan klasörler ve üretilen dosyalar denetlenmez
    ignores: ['dist/*', 'mobile/*', 'backend/*', '.expo/*', 'api/schema.d.ts'],
  },
]);
