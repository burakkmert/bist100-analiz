// SDK 54: babel-preset-expo, Reanimated/Worklets eklentisini otomatik ekler.
module.exports = function (api) {
  api.cache(true);
  return { presets: ['babel-preset-expo'] };
};
