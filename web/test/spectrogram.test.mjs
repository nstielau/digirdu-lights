import assert from 'node:assert/strict';
import test from 'node:test';

const valid = {
  min_frequency_hz: 31.25,
  max_frequency_hz: 8000,
  min_dbfs: -90,
  max_dbfs: 0,
  rows: 2,
  columns: 2,
  frames: [[0, 255], [64, 128]],
};

async function loadModule() {
  return import('../spectrogram.mjs').catch(() => null);
}

test('missing spectrogram remains backward compatible', async () => {
  const module = await loadModule();
  assert.ok(module, 'spectrogram module should exist');
  assert.equal(module.normalizeSpectrogram(undefined, 2), null);
});

test('normalizes aligned byte frames and rasterizes high frequencies on top', async () => {
  const module = await loadModule();
  assert.ok(module, 'spectrogram module should exist');
  const normalized = module.normalizeSpectrogram(valid, 2);
  const rgba = module.spectrogramRgba(normalized);
  assert.equal(rgba.length, 2 * 2 * 4);
  assert.deepEqual([...rgba.slice(0, 4)], [255, 207, 106, 255]);
  assert.deepEqual([...rgba.slice(8, 12)], [7, 11, 35, 255]);
});

test('rejects malformed or horizontally misaligned spectrograms', async () => {
  const module = await loadModule();
  assert.ok(module, 'spectrogram module should exist');
  assert.throws(
    () => module.normalizeSpectrogram({...valid, columns: 3}, 2),
    /columns/,
  );
  assert.throws(
    () => module.normalizeSpectrogram(
      {...valid, frames: [[0, 256], [64, 128]]},
      2,
    ),
    /byte/,
  );
  assert.throws(
    () => module.normalizeSpectrogram({...valid, min_dbfs: 0, max_dbfs: -90}, 2),
    /dB/,
  );
});
