// Plays exported firmware frames; never captures audio or sends device commands.
export async function initReplay() {
  const play = document.querySelector('#replay-play');
  const seek = document.querySelector('#replay-seek');
  const time = document.querySelector('#replay-time');
  const section = document.querySelector('#replay-section');
  const grids = document.querySelector('#replay-grids');
  try {
    const response = await fetch('./assets/effects-replay.json');
    if (!response.ok) throw new Error('Replay unavailable');
    const data = await response.json();
    const contexts = data.names.map((name, index) => {
      const figure = document.createElement('figure');
      const caption = document.createElement('figcaption');
      const link = document.createElement('a');
      link.href = '#' + name.toLowerCase();
      link.textContent = `${index + 1} · ${name}`;
      caption.append(link);
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 160;
      canvas.setAttribute('role', 'img');
      canvas.setAttribute('aria-label', `${name}: recorded 8 by 4 LED preview`);
      figure.append(caption, canvas);
      grids.append(figure);
      return canvas.getContext('2d');
    });
    let index = 0, playing = false, started = 0, request;
    seek.max = data.frames.length - 1;
    function draw() {
      const raw = atob(data.frames[index]);
      contexts.forEach((ctx, effect) => {
        ctx.clearRect(0, 0, 320, 160);
        for (let pixel = 0; pixel < 32; pixel++) {
          const offset = effect * 96 + pixel * 3;
          const gain = 1 / data.brightness;
          const g = raw.charCodeAt(offset) * gain;
          const r = raw.charCodeAt(offset + 1) * gain;
          const b = raw.charCodeAt(offset + 2) * gain;
          ctx.fillStyle = `rgb(${r},${g},${b})`;
          ctx.beginPath();
          ctx.arc(pixel % 8 * 40 + 20, Math.floor(pixel / 8) * 40 + 20, 15, 0, Math.PI * 2);
          ctx.fill();
        }
      });
      seek.value = index;
      time.textContent = `${(index / data.fps).toFixed(1)} / ${data.duration.toFixed(1)} s`;
      seek.setAttribute('aria-valuetext', `${(index / data.fps).toFixed(1)} seconds, ${data.sections[index]}`);
      section.textContent = data.sections[index];
    }
    function pause() {
      playing = false;
      cancelAnimationFrame(request);
      play.textContent = 'Play replay';
    }
    function tick(now) {
      index = Math.min(data.frames.length - 1, Math.floor((now - started) * data.fps / 1000));
      draw();
      if (index === data.frames.length - 1) pause();
      else request = requestAnimationFrame(tick);
    }
    play.addEventListener('click', () => {
      if (playing) return pause();
      playing = true;
      if (index === data.frames.length - 1) index = 0;
      started = performance.now() - index / data.fps * 1000;
      play.textContent = 'Pause replay';
      request = requestAnimationFrame(tick);
    });
    seek.addEventListener('input', () => {
      index = Number(seek.value);
      started = performance.now() - index / data.fps * 1000;
      draw();
    });
    // Returning to a hidden tab must not skip ahead through the performance.
    document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
    draw();
    play.disabled = seek.disabled = false;
  } catch {
    grids.replaceChildren();
    section.textContent = 'The saved replay could not load. You can still read the effect descriptions below. Reload to try again.';
  }
}
