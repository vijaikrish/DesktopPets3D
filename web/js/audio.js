// WebAudio playback of the pet's sound bank + lip-sync envelopes (the jaw follows the sound's loudness).
export class AudioPlayer {
  constructor() {
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    this.cache = new Map();
    this.active = [];
    this.volume = 0.8;
    this.muted = false;
    this.started = 0;
  }

  setVolume(v, muted) {
    this.volume = v; this.muted = !!muted;
    this.master.gain.value = this.muted ? 0 : Math.max(0, Math.min(1, v));
  }

  async load(url) {
    if (!this.cache.has(url)) {
      this.cache.set(url, fetch(url).then((r) => r.arrayBuffer()).then((b) => this.ctx.decodeAudioData(b)));
    }
    return this.cache.get(url);
  }

  preload(urls) { for (const u of urls) this.load(u).catch(() => {}); }

  async play(cmd) {
    if (this.muted) return null;
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    const buf = await this.load(cmd.url);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = cmd.rate || 1;
    const g = this.ctx.createGain();
    g.gain.value = Math.pow(10, (cmd.gain_db || 0) / 20);
    src.connect(g).connect(this.master);
    src.start();
    this.started++;
    const item = { t0: performance.now(), dur: buf.duration / (cmd.rate || 1), env: cmd.env, jaw: cmd.jaw_deg || 0, rate: cmd.rate || 1 };
    this.active.push(item);
    src.onended = () => { this.active = this.active.filter((a) => a !== item); };
    return item;
  }

  // degrees of extra jaw opening right now (max over lip-synced sounds)
  jawNow(now = performance.now()) {
    let best = 0;
    for (const a of this.active) {
      if (!a.env || !a.jaw) continue;
      const i = Math.floor(((now - a.t0) / 1000) * 60 * a.rate);
      if (i >= 0 && i < a.env.length) best = Math.max(best, a.env[i] * a.jaw);
    }
    return best;
  }

  speaking() { return this.active.some((a) => a.env && a.jaw); }
}
