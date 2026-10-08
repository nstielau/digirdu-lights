export function localReviewDataUrl(location) {
  if (!['localhost', '127.0.0.1'].includes(location.hostname)) return null;
  return new URLSearchParams(location.search).get('data');
}
