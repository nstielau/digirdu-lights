export function localReviewDataUrl(location) {
  if (!['localhost', '127.0.0.1'].includes(location.hostname)) return null;
  return new URLSearchParams(location.search).get('data');
}

export function localReviewCatalogUrl(location) {
  if (!['localhost', '127.0.0.1'].includes(location.hostname)) return null;
  return new URLSearchParams(location.search).get('catalog');
}

export function reviewEffectNames(effects) {
  const frames = effects?.frames;
  if (!frames || typeof frames !== 'object' || Array.isArray(frames)) return [];
  const declared = Array.isArray(effects.effects) ? effects.effects : Object.keys(frames);
  return [...new Set(declared)].filter((name) => (
    typeof name === 'string'
    && Array.isArray(frames[name]?.['0'])
    && frames[name]['0'].length > 0
  ));
}

export function selectReviewEffect(effects, preferred) {
  const names = reviewEffectNames(effects);
  return names.includes(preferred) ? preferred : (names[0] ?? null);
}

export function reviewEffectFrames(effects, effect) {
  const rows = effects?.frames?.[effect]?.['0'];
  return Array.isArray(rows) ? rows : [];
}

export function reviewPixelChannels(pixel) {
  if (!Array.isArray(pixel) || pixel.length < 3) return [0, 0, 0];
  return pixel.slice(0, 3).map((value) => {
    const channel = Number(value);
    return Number.isFinite(channel) ? Math.max(0, Math.min(255, channel)) : 0;
  });
}
