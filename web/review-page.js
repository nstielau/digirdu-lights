import {
  localReviewCatalogUrl,
  localReviewDataUrl,
  reviewEffectFrames,
  reviewEffectNames,
  reviewPixelChannels,
  selectReviewEffect,
} from './review-mode.mjs';
import {normalizeSpectrogram, paintSpectrogram} from './spectrogram.mjs';

const state = {
  bundle: null,
  timeMs: 0,
  playing: false,
  selectedLabel: null,
  zoom: 1,
  replayEndMs: null,
  enabledEventGroups: new Set(),
  effect: 'Spectrum',
};

const KNOWN_EVENT_GROUPS = [
  {id: 'transient', label: 'Transient', types: ['transient'], enabled: false},
  {id: 'yell', label: 'Yell', types: ['yell'], enabled: true},
  {id: 'drone-boundaries', label: 'Drone boundaries', types: ['drone_start', 'drone_stop'], enabled: true},
];

const WAVEFORM_DRAG_THRESHOLD_PX = 5;
const waveformGesture = {
  pointerId: null,
  startClientX: 0,
  startScrollLeft: 0,
  dragged: false,
};

const audio = document.querySelector('#review-audio');
const play = document.querySelector('#review-play');
const replay = document.querySelector('#review-replay');
const position = document.querySelector('#review-position');
const zoom = document.querySelector('#review-zoom');
const timeOutput = document.querySelector('#review-time');
const status = document.querySelector('#review-status');
const waveform = document.querySelector('#review-waveform');
const labels = document.querySelector('#review-labels');
const events = document.querySelector('#review-events');
const eventFilters = document.querySelector('#review-event-filters');
const features = document.querySelector('#review-features');
const comparison = document.querySelector('#review-comparison');
const led = document.querySelector('#review-led');
const effectSelect = document.querySelector('#review-effect');
const selectedLabel = document.querySelector('#review-selected-label');

function setStatus(message, isError = false) {
  status.textContent = message;
  status.dataset.state = isError ? 'error' : 'ready';
}

function finiteNumber(value, name) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${name} must be a finite number`);
  }
  return value;
}

function normalizeRows(value, name) {
  if (Array.isArray(value)) return value;
  if (value && Array.isArray(value[name])) return value[name];
  return [];
}

function normalizeBundle(bundle) {
  if (!bundle || typeof bundle !== 'object') throw new Error('Review bundle must be an object');
  const durationMs = finiteNumber(bundle.duration_ms, 'duration_ms');
  if (durationMs <= 0) throw new Error('duration_ms must be positive');
  if (bundle.audio_url !== undefined && typeof bundle.audio_url !== 'string') {
    throw new Error('audio_url must be a string');
  }
  const waveformRows = Array.isArray(bundle.waveform) ? bundle.waveform : [];
  return {
    ...bundle,
    duration_ms: durationMs,
    waveform: waveformRows,
    spectrogram: normalizeSpectrogram(bundle.spectrogram, waveformRows.length),
    labels: normalizeRows(bundle.labels, 'labels'),
    events: normalizeRows(bundle.events, 'events'),
    features: normalizeRows(bundle.features, 'features'),
    comparison: bundle.comparison && typeof bundle.comparison === 'object' ? bundle.comparison : {},
    effects: bundle.effects && typeof bundle.effects === 'object' ? bundle.effects : {frames: {}},
  };
}

function clampTime(timeMs) {
  return Math.max(0, Math.min(state.bundle.duration_ms, finiteNumber(timeMs, 'time_ms')));
}

function rowTime(row) {
  return Number.isFinite(row?.time_ms) ? row.time_ms : row?.start_ms;
}

function rowEnd(row) {
  return Number.isFinite(row?.end_ms) ? row.end_ms : rowTime(row);
}

function nearestRow(rows, timeMs) {
  if (!rows.length) return null;
  return rows.reduce((best, row) => {
    if (!best) return row;
    return Math.abs(rowTime(row) - timeMs) < Math.abs(rowTime(best) - timeMs) ? row : best;
  }, null);
}

function percentAt(timeMs) {
  return state.bundle.duration_ms ? timeMs / state.bundle.duration_ms * 100 : 0;
}

function frequencyLabel(value) {
  return value >= 1000
    ? `${Number((value / 1000).toFixed(2))} kHz`
    : `${Math.round(value)} Hz`;
}

function frequencyAxis(spectrogram) {
  const axis = document.createElement('div');
  const high = document.createElement('span');
  const low = document.createElement('span');
  axis.className = 'spectrogram-axis';
  high.textContent = frequencyLabel(spectrogram.maxFrequencyHz);
  low.textContent = frequencyLabel(spectrogram.minFrequencyHz);
  axis.append(high, low);
  return axis;
}

function intensityLegend(spectrogram) {
  const legend = document.createElement('div');
  legend.className = 'spectrogram-legend';
  legend.textContent = `${spectrogram.minDbfs} dBFS → ${spectrogram.maxDbfs} dBFS`;
  return legend;
}

function renderSpectrogramCanvas() {
  const canvas = waveform.querySelector('#review-spectrogram');
  if (canvas && state.bundle?.spectrogram) {
    paintSpectrogram(
      canvas,
      state.bundle.spectrogram,
      window.devicePixelRatio || 1,
    );
  }
}

function renderWaveform() {
  const track = waveform.querySelector('.timeline-track');
  track.replaceChildren();
  track.style.setProperty('--wave-count', String(Math.max(1, state.bundle.waveform.length)));
  const waveformRegion = document.createElement('div');
  waveformRegion.className = 'waveform-region';
  state.bundle.waveform.forEach((sample, index) => {
    const bar = document.createElement('span');
    const magnitude = Math.max(0, Math.min(1, Math.abs(Number(sample) || 0)));
    bar.className = 'wave-bar';
    bar.style.left = `${index / Math.max(1, state.bundle.waveform.length) * 100}%`;
    bar.style.height = `${Math.max(4, magnitude * 70)}px`;
    waveformRegion.append(bar);
  });
  const labelLayer = document.createElement('div');
  labelLayer.className = 'label-overlay-layer';
  waveformRegion.append(labelLayer);
  const eventLayer = document.createElement('div');
  eventLayer.className = 'event-overlay-layer';
  waveformRegion.append(eventLayer);
  const spectrogramRegion = document.createElement('div');
  spectrogramRegion.className = 'spectrogram-region';
  if (state.bundle.spectrogram) {
    const canvas = document.createElement('canvas');
    canvas.id = 'review-spectrogram';
    canvas.className = 'spectrogram-canvas';
    canvas.dataset.columns = String(state.bundle.spectrogram.columns);
    canvas.setAttribute('role', 'img');
    canvas.setAttribute(
      'aria-label',
      `Log-frequency spectrogram from ${state.bundle.spectrogram.minFrequencyHz} Hz to ${state.bundle.spectrogram.maxFrequencyHz} Hz, ${state.bundle.spectrogram.minDbfs} to ${state.bundle.spectrogram.maxDbfs} dBFS`,
    );
    spectrogramRegion.append(
      canvas,
      frequencyAxis(state.bundle.spectrogram),
      intensityLegend(state.bundle.spectrogram),
    );
  } else {
    const message = document.createElement('p');
    message.className = 'spectrogram-empty';
    message.textContent = 'Spectrogram unavailable for this older review bundle.';
    spectrogramRegion.append(message);
  }
  const cursor = document.createElement('span');
  cursor.className = 'track-cursor';
  track.append(waveformRegion, spectrogramRegion, cursor);
  requestAnimationFrame(renderSpectrogramCanvas);
}

function labelIsActive(label, timeMs) {
  return timeMs >= rowTime(label) && timeMs <= rowEnd(label);
}

function updateLabelState(timeMs) {
  state.bundle.labels.forEach((label, index) => {
    const active = labelIsActive(label, timeMs);
    const selected = state.selectedLabel === index;
    const nodes = [
      labels.querySelector(`[data-label-index="${index}"]`),
      waveform.querySelector(`.label-overlay[data-label-index="${index}"]`),
    ].filter(Boolean);
    nodes.forEach((node) => {
      node.dataset.active = String(active);
      node.dataset.selected = String(selected);
      node.setAttribute('aria-pressed', String(selected));
    });
  });
}

function selectLabel(index) {
  const label = state.bundle.labels[index];
  state.selectedLabel = index;
  selectedLabel.textContent = `Selected: ${label.type} · ${formatMs(rowTime(label))}${rowEnd(label) !== rowTime(label) ? `–${formatMs(rowEnd(label))}` : ''}`;
  replay.disabled = false;
  updateLabelState(state.timeMs);
  setTime(rowTime(label));
}

function renderLabelOverlays() {
  const layer = waveform.querySelector('.label-overlay-layer');
  layer.replaceChildren();
  state.bundle.labels.forEach((label, index) => {
    const start = rowTime(label);
    const end = rowEnd(label);
    const marker = document.createElement('button');
    const width = end > start ? percentAt(end) - percentAt(start) : 0.75;
    marker.type = 'button';
    marker.className = 'label-overlay';
    marker.dataset.labelIndex = String(index);
    marker.style.left = `${percentAt(start)}%`;
    marker.style.width = `${Math.max(0.75, width)}%`;
    marker.textContent = label.type;
    marker.setAttribute('aria-label', `${label.type} timeline label at ${formatMs(start)}`);
    marker.addEventListener('click', () => selectLabel(index));
    layer.append(marker);
  });
}

function renderLabels() {
  labels.replaceChildren();
  if (!state.bundle.labels.length) {
    labels.append(emptyMessage('No human labels in this bundle.'));
    renderLabelOverlays();
    return;
  }
  state.bundle.labels.forEach((label, index) => {
    const button = document.createElement('button');
    const end = rowEnd(label);
    button.type = 'button';
    button.dataset.labelIndex = String(index);
    button.textContent = `${label.type} · ${formatMs(rowTime(label))}${end !== rowTime(label) ? `–${formatMs(end)}` : ''}`;
    button.setAttribute('aria-label', `${label.type} label at ${formatMs(rowTime(label))}`);
    button.setAttribute('aria-pressed', state.selectedLabel === index ? 'true' : 'false');
    button.addEventListener('click', () => selectLabel(index));
    labels.append(button);
  });
  renderLabelOverlays();
  updateLabelState(state.timeMs);
}

function updateEventState(timeMs) {
  state.bundle.events.forEach((event, index) => {
    const active = timeMs >= rowTime(event) && timeMs <= rowEnd(event);
    const nodes = [
      events.querySelector(`[data-event-index="${index}"]`),
      waveform.querySelector(`.event-overlay[data-event-index="${index}"]`),
    ].filter(Boolean);
    nodes.forEach((node) => {
      node.dataset.active = String(active);
      if (node.tagName === 'LI') node.classList.toggle('event-active', active);
    });
  });
}

function eventGroupForType(type) {
  const knownGroup = KNOWN_EVENT_GROUPS.find((group) => group.types.includes(type));
  if (knownGroup) return knownGroup;
  return {
    id: `unknown:${type}`,
    label: readableEventType(type),
    types: [type],
    enabled: true,
  };
}

function readableEventType(type) {
  const words = String(type || 'unknown').replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function availableEventGroups() {
  const groups = KNOWN_EVENT_GROUPS.map((group) => ({
    ...group,
    count: state.bundle.events.filter((event) => group.types.includes(event.type)).length,
  })).filter((group) => group.count > 0);
  const unknownGroups = new Map();
  state.bundle.events.forEach((event) => {
    if (KNOWN_EVENT_GROUPS.some((group) => group.types.includes(event.type))) return;
    const group = eventGroupForType(event.type);
    const existing = unknownGroups.get(group.id);
    if (existing) existing.count += 1;
    else unknownGroups.set(group.id, {...group, count: 1});
  });
  return [...groups, ...unknownGroups.values()];
}

function eventIsVisible(event) {
  const group = eventGroupForType(event.type);
  return state.enabledEventGroups.has(group.id);
}

function renderEventFilters() {
  eventFilters.replaceChildren();
  state.enabledEventGroups.clear();
  const groups = availableEventGroups();
  eventFilters.hidden = groups.length === 0;
  groups.forEach((group) => {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = group.enabled;
    if (group.enabled) state.enabledEventGroups.add(group.id);
    input.addEventListener('change', () => {
      if (input.checked) state.enabledEventGroups.add(group.id);
      else state.enabledEventGroups.delete(group.id);
      renderEvents(state.timeMs);
    });
    label.append(input, `${group.label} (${group.count})`);
    eventFilters.append(label);
  });
}

function renderEventOverlays() {
  const layer = waveform.querySelector('.event-overlay-layer');
  layer.replaceChildren();
  state.bundle.events.forEach((event, index) => {
    if (!eventIsVisible(event)) return;
    const marker = document.createElement('button');
    const timeMs = rowTime(event);
    marker.type = 'button';
    marker.className = 'event-overlay';
    marker.dataset.eventIndex = String(index);
    marker.style.left = `${percentAt(timeMs)}%`;
    marker.textContent = event.type;
    marker.setAttribute('aria-label', `${event.type} detected at ${formatMs(timeMs)}`);
    marker.addEventListener('click', () => setTime(timeMs));
    layer.append(marker);
  });
}

function renderEvents(timeMs) {
  events.replaceChildren();
  if (!state.bundle.events.length) {
    events.append(emptyMessage('No detected events in this bundle.'));
    renderEventOverlays();
    return;
  }
  const visibleEvents = state.bundle.events
    .map((event, index) => ({event, index}))
    .filter(({event}) => eventIsVisible(event));
  if (!visibleEvents.length) {
    events.append(emptyMessage('No detected events selected.'));
    renderEventOverlays();
    return;
  }
  visibleEvents.forEach(({event, index}) => {
    const item = document.createElement('li');
    const time = rowTime(event);
    const active = timeMs >= time && timeMs <= rowEnd(event);
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `${event.type} · ${formatMs(time)}${event.confidence === undefined ? '' : ` · ${(event.confidence * 100).toFixed(0)}%`}`;
    button.setAttribute('aria-label', `${event.type} detected at ${formatMs(time)}`);
    button.addEventListener('click', () => setTime(time));
    item.dataset.eventIndex = String(index);
    item.dataset.active = active ? 'true' : 'false';
    item.className = active ? 'event-active' : '';
    item.append(button);
    events.append(item);
  });
  renderEventOverlays();
  updateEventState(timeMs);
}

function renderFeatureCursor(timeMs) {
  const feature = nearestRow(state.bundle.features, timeMs);
  features.dataset.timeMs = String(feature?.time_ms ?? timeMs);
  features.replaceChildren();
  if (!feature) {
    features.append(emptyMessage('No derived features in this bundle.'));
    return;
  }
  const values = [
    ['time', formatMs(feature.time_ms)],
    ['volume', feature.volume],
    ['drone', feature.drone],
    ['vocal', feature.vocal],
    ['transient', feature.transient_strength],
  ];
  values.forEach(([name, value]) => {
    const term = document.createElement('div');
    const title = document.createElement('dt');
    const detail = document.createElement('dd');
    title.textContent = name;
    detail.textContent = typeof value === 'number' ? value.toFixed(2) : String(value);
    term.append(title, detail);
    features.append(term);
  });
}

function percentage(value) {
  return `${(Math.max(0, Math.min(1, Number(value) || 0)) * 100).toFixed(0)}%`;
}

function renderComparison() {
  comparison.replaceChildren();
  const reports = Object.entries(state.bundle.comparison);
  if (!reports.length) {
    comparison.append(emptyMessage('No human/detector comparison in this bundle.'));
    return;
  }
  reports.forEach(([type, report]) => {
    const item = document.createElement('li');
    item.className = 'review-metric';
    if (Number.isFinite(report?.precision)) {
      item.textContent = `${type} · ${percentage(report.precision)} precision · ${percentage(report.recall)} recall · ${percentage(report.f1)} F1 · TP ${report.true_positive ?? 0} · FP ${report.false_positive ?? 0} · FN ${report.false_negative ?? 0}`;
    } else {
      item.textContent = `${type} · ${percentage(report?.intersection_over_union)} interval overlap · ${formatMs(report?.false_active_ms ?? 0)} false active · ${formatMs(report?.false_inactive_ms ?? 0)} false inactive`;
    }
    comparison.append(item);
  });
}

function renderEffectOptions() {
  const names = reviewEffectNames(state.bundle?.effects);
  state.effect = selectReviewEffect(state.bundle?.effects, state.effect);
  effectSelect.replaceChildren();
  names.forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    effectSelect.append(option);
  });
  effectSelect.disabled = state.effect === null;
  if (state.effect !== null) effectSelect.value = state.effect;
}

function renderLedFrame(timeMs) {
  const effect = state.bundle ? state.effect : null;
  const frame = nearestRow(reviewEffectFrames(state.bundle?.effects, effect), timeMs);
  led.dataset.timeMs = String(frame?.time_ms ?? timeMs);
  led.dataset.effect = effect || '';
  led.setAttribute(
    'aria-label',
    effect
      ? `Virtual consumer ${effect} frame at ${formatMs(frame?.time_ms ?? timeMs)}`
      : 'Virtual consumer frame unavailable',
  );
  led.replaceChildren();
  const pixels = frame?.pixels_rgb || [];
  for (let index = 0; index < 32; index += 1) {
    const pixel = document.createElement('span');
    const channels = reviewPixelChannels(pixels[index]);
    pixel.className = 'led-pixel';
    pixel.style.backgroundColor = `rgb(${channels.join(',')})`;
    pixel.setAttribute('aria-label', `LED ${index + 1}: RGB ${channels.join(', ')}`);
    led.append(pixel);
  }
}

function emptyMessage(message) {
  const item = document.createElement('li');
  item.className = 'review-empty';
  item.textContent = message;
  return item;
}

function formatMs(value) {
  return `${(value / 1000).toFixed(2)} s`;
}

function setTime(timeMs, {seekAudio = true} = {}) {
  if (!state.bundle) return;
  state.timeMs = clampTime(timeMs);
  if (seekAudio && (Number.isFinite(audio.duration) || audio.src)) {
    audio.currentTime = state.timeMs / 1000;
  }
  position.value = String(Math.round(state.timeMs));
  timeOutput.textContent = formatMs(state.timeMs);
  waveform.dataset.timeMs = String(Math.round(state.timeMs));
  const cursor = waveform.querySelector('.track-cursor');
  if (cursor) {
    cursor.dataset.timeMs = String(Math.round(state.timeMs));
    cursor.style.left = `${percentAt(state.timeMs)}%`;
  }
  updateLabelState(state.timeMs);
  renderFeatureCursor(state.timeMs);
  updateEventState(state.timeMs);
  renderLedFrame(state.timeMs);
  if (state.replayEndMs !== null && state.timeMs >= state.replayEndMs) stopPlayback();
}

function stopPlayback() {
  audio.pause();
  state.playing = false;
  state.replayEndMs = null;
  play.textContent = 'Play';
}

async function startPlayback() {
  state.playing = true;
  play.textContent = 'Pause';
  try {
    await audio.play();
  } catch (error) {
    stopPlayback();
    setStatus(`Audio could not play: ${error.message || 'playback was rejected'}`, true);
  }
}

async function replaySelectedLabel() {
  if (state.selectedLabel === null) return;
  const label = state.bundle.labels[state.selectedLabel];
  const start = Math.max(0, rowTime(label) - 500);
  state.replayEndMs = Math.min(state.bundle.duration_ms, rowEnd(label) + 500);
  setTime(start);
  await startPlayback();
}

function setZoom(value) {
  state.zoom = Math.max(1, Math.min(8, Number(value)));
  waveform.dataset.zoom = String(state.zoom);
  waveformTrack().style.setProperty('--timeline-zoom', state.zoom);
  requestAnimationFrame(renderSpectrogramCanvas);
}

function waveformTrack() {
  return waveform.querySelector('.timeline-track');
}

function clearWaveformGesture(pointerId, {release = true} = {}) {
  if (waveformGesture.pointerId !== pointerId) return;
  if (release && waveform.hasPointerCapture(pointerId)) {
    waveform.releasePointerCapture(pointerId);
  }
  waveformGesture.pointerId = null;
  waveformGesture.dragged = false;
  waveform.dataset.panning = 'false';
}

function seekWaveformAt(clientX) {
  const rect = waveformTrack().getBoundingClientRect();
  if (!rect.width) return;
  const fraction = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  setTime(fraction * state.bundle.duration_ms);
}

function waveformPointerDown(event) {
  if (!event.isPrimary || event.button !== 0 || waveformGesture.pointerId !== null) return;
  if (event.target.closest('.label-overlay,.event-overlay')) return;
  waveformGesture.pointerId = event.pointerId;
  waveformGesture.startClientX = event.clientX;
  waveformGesture.startScrollLeft = waveform.scrollLeft;
  waveformGesture.dragged = false;
  waveform.setPointerCapture(event.pointerId);
}

function waveformPointerMove(event) {
  if (waveformGesture.pointerId !== event.pointerId) return;
  const delta = event.clientX - waveformGesture.startClientX;
  if (!waveformGesture.dragged && Math.abs(delta) > WAVEFORM_DRAG_THRESHOLD_PX) {
    waveformGesture.dragged = true;
    waveform.dataset.panning = 'true';
  }
  if (!waveformGesture.dragged) return;
  waveform.scrollLeft = waveformGesture.startScrollLeft - delta;
  event.preventDefault();
}

function waveformPointerUp(event) {
  if (waveformGesture.pointerId !== event.pointerId) return;
  if (!waveformGesture.dragged) seekWaveformAt(event.clientX);
  clearWaveformGesture(event.pointerId);
}

function configureBundle(bundle, sourceUrl) {
  stopPlayback();
  state.bundle = normalizeBundle(bundle);
  state.selectedLabel = null;
  state.replayEndMs = null;
  zoom.value = '1';
  waveform.scrollLeft = 0;
  position.max = String(Math.round(state.bundle.duration_ms));
  position.disabled = false;
  zoom.disabled = false;
  play.disabled = !state.bundle.audio_url;
  replay.disabled = true;
  renderEffectOptions();
  renderWaveform();
  renderLabels();
  renderEventFilters();
  renderEvents(0);
  renderComparison();
  if (state.bundle.audio_url) {
    audio.src = new URL(state.bundle.audio_url, sourceUrl).href;
  } else {
    setStatus('Review loaded; this bundle has no audio URL.');
  }
  setZoom(1);
  setTime(0, {seekAudio: false});
  if (state.bundle.audio_url) setStatus('Review loaded.');
}

function clearReview() {
  stopPlayback();
  state.bundle = null;
  state.timeMs = 0;
  state.selectedLabel = null;
  state.replayEndMs = null;
  state.enabledEventGroups.clear();
  audio.removeAttribute('src');
  audio.load();
  play.disabled = true;
  replay.disabled = true;
  position.disabled = true;
  position.max = '0';
  position.value = '0';
  zoom.disabled = true;
  zoom.value = '1';
  timeOutput.textContent = '0.00 s';
  waveform.scrollLeft = 0;
  waveform.dataset.zoom = '1';
  waveform.dataset.timeMs = '0';
  waveform.querySelector('.timeline-track').replaceChildren();
  eventFilters.replaceChildren();
  eventFilters.hidden = true;
  labels.replaceChildren();
  events.replaceChildren();
  features.replaceChildren();
  comparison.replaceChildren();
  effectSelect.replaceChildren();
  effectSelect.disabled = true;
  renderLedFrame(0);
  selectedLabel.textContent = 'No label selected.';
}

async function loadBundle(dataUrl) {
  try {
    const response = await fetch(dataUrl, {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    configureBundle(await response.json(), response.url);
  } catch (error) {
    play.disabled = true;
    replay.disabled = true;
    position.disabled = true;
    zoom.disabled = true;
    setStatus(`Review could not load: ${error.message || 'invalid bundle'}`, true);
  }
}

audio.addEventListener('timeupdate', () => {
  if (state.playing) setTime(audio.currentTime * 1000, {seekAudio: false});
});
audio.addEventListener('ended', () => stopPlayback());
audio.addEventListener('error', () => {
  setStatus('Audio could not load for this review.', true);
  play.disabled = true;
  stopPlayback();
});
position.addEventListener('input', () => setTime(Number(position.value)));
zoom.addEventListener('input', () => setZoom(zoom.value));
play.addEventListener('click', () => {
  if (state.playing) stopPlayback();
  else startPlayback();
});
replay.addEventListener('click', replaySelectedLabel);
effectSelect.addEventListener('change', () => {
  state.effect = effectSelect.value;
  renderLedFrame(state.timeMs);
});
waveform.addEventListener('pointerdown', waveformPointerDown);
waveform.addEventListener('pointermove', waveformPointerMove);
waveform.addEventListener('pointerup', waveformPointerUp);
waveform.addEventListener('pointercancel', (event) => clearWaveformGesture(event.pointerId));
waveform.addEventListener('lostpointercapture', (event) => clearWaveformGesture(event.pointerId, {release: false}));

renderLedFrame(0);
const spectrogramResizeObserver = new ResizeObserver(renderSpectrogramCanvas);
spectrogramResizeObserver.observe(waveformTrack());

const localCatalogUrl = localReviewCatalogUrl(window.location);
const localDataUrl = localReviewDataUrl(window.location);
if (localCatalogUrl) {
  document.querySelector('#review-protected').hidden = false;
  import('./review-local.js')
    .then(({initLocalReview}) => initLocalReview({clearReview, configureBundle, setStatus}, localCatalogUrl))
    .catch(() => setStatus('Local recording catalog could not start.', true));
} else if (localDataUrl) {
  document.querySelector('#review-protected').hidden = false;
  loadBundle(localDataUrl);
} else {
  import('./review-online.js')
    .then(({initOnlineReview}) => initOnlineReview({clearReview, configureBundle, setStatus}))
    .catch(() => setStatus('Online review could not start.', true));
}

export {clearReview, configureBundle, setStatus, setTime, state, stopPlayback};
