const PALETTE = [
  {at: 0, rgb: [7, 11, 35]},
  {at: 0.35, rgb: [22, 93, 117]},
  {at: 0.68, rgb: [212, 91, 114]},
  {at: 1, rgb: [255, 207, 106]},
];

function finite(value, name) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${name} must be finite`);
  }
  return value;
}

function positiveInteger(value, name) {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export function normalizeSpectrogram(value, waveformColumns) {
  if (value === undefined) return null;
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('spectrogram must be an object');
  }
  const rows = positiveInteger(value.rows, 'spectrogram rows');
  const columns = positiveInteger(value.columns, 'spectrogram columns');
  if (columns !== waveformColumns) {
    throw new Error('spectrogram columns must match waveform');
  }
  const minFrequencyHz = finite(
    value.min_frequency_hz,
    'minimum frequency',
  );
  const maxFrequencyHz = finite(
    value.max_frequency_hz,
    'maximum frequency',
  );
  if (minFrequencyHz <= 0 || maxFrequencyHz <= minFrequencyHz) {
    throw new Error('spectrogram frequency bounds are invalid');
  }
  const minDbfs = finite(value.min_dbfs, 'minimum dBFS');
  const maxDbfs = finite(value.max_dbfs, 'maximum dBFS');
  if (maxDbfs <= minDbfs) {
    throw new Error('spectrogram dB bounds are invalid');
  }
  if (!Array.isArray(value.frames) || value.frames.length !== columns) {
    throw new Error('spectrogram frame count is invalid');
  }
  const frames = value.frames.map((frame) => {
    if (!Array.isArray(frame) || frame.length !== rows) {
      throw new Error('spectrogram row count is invalid');
    }
    return frame.map((sample) => {
      if (!Number.isInteger(sample) || sample < 0 || sample > 255) {
        throw new Error('spectrogram values must be bytes');
      }
      return sample;
    });
  });
  return {
    minFrequencyHz,
    maxFrequencyHz,
    minDbfs,
    maxDbfs,
    rows,
    columns,
    frames,
  };
}

function colorFor(value) {
  const position = value / 255;
  const right = PALETTE.findIndex((stop) => position <= stop.at);
  if (right <= 0) return PALETTE[0].rgb;
  const low = PALETTE[right - 1];
  const high = PALETTE[right];
  const mix = (position - low.at) / (high.at - low.at);
  return low.rgb.map((channel, index) => (
    Math.round(channel + (high.rgb[index] - channel) * mix)
  ));
}

export function spectrogramRgba(spectrogram) {
  const rgba = new Uint8ClampedArray(
    spectrogram.columns * spectrogram.rows * 4,
  );
  spectrogram.frames.forEach((frame, x) => frame.forEach((value, row) => {
    const y = spectrogram.rows - 1 - row;
    const offset = (y * spectrogram.columns + x) * 4;
    rgba.set([...colorFor(value), 255], offset);
  }));
  return rgba;
}

export function paintSpectrogram(
  canvas,
  spectrogram,
  devicePixelRatio = 1,
) {
  const width = Math.max(
    1,
    Math.round(canvas.clientWidth * devicePixelRatio),
  );
  const height = Math.max(
    1,
    Math.round(canvas.clientHeight * devicePixelRatio),
  );
  canvas.width = width;
  canvas.height = height;
  const source = document.createElement('canvas');
  source.width = spectrogram.columns;
  source.height = spectrogram.rows;
  source.getContext('2d').putImageData(
    new ImageData(
      spectrogramRgba(spectrogram),
      spectrogram.columns,
      spectrogram.rows,
    ),
    0,
    0,
  );
  const context = canvas.getContext('2d');
  context.imageSmoothingEnabled = false;
  context.drawImage(source, 0, 0, width, height);
}
