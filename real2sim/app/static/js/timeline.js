// Play / pause / scrub the scene time. Calls onTime(t) whenever the time changes.

import { num } from "./format.js";

export class Timeline {
  constructor({ play, slider, label, speed }, onTime) {
    Object.assign(this, { playButton: play, slider, label, speedSelect: speed, onTime });
    this.duration = 0;
    this.time = 0;
    this.playing = false;
    this._last = null;
    play.addEventListener("click", () => this.toggle());
    slider.addEventListener("input", () => this.setTime(Number(slider.value)));
  }

  setDuration(duration) {
    this.duration = duration;
    this.slider.max = String(duration);
    this.setTime(0);
  }

  setTime(t) {
    this.time = Math.min(Math.max(t, 0), this.duration);
    this.slider.value = String(this.time);
    this.label.textContent = `${num(this.time, 1)} s`;
    this.onTime(this.time);
  }

  toggle() {
    this.playing = !this.playing;
    this.playButton.textContent = this.playing ? "❚❚" : "▶";
    this.playButton.setAttribute("aria-label", this.playing ? "Tạm dừng" : "Phát");
    if (this.playing) {
      if (this.time >= this.duration) this.setTime(0);
      this._last = null;
      requestAnimationFrame((ts) => this._tick(ts));
    }
  }

  _tick(timestamp) {
    if (!this.playing) return;
    if (this._last !== null) {
      const speed = Number(this.speedSelect.value);
      this.setTime(this.time + ((timestamp - this._last) / 1000) * speed);
      if (this.time >= this.duration) { this.toggle(); return; }
    }
    this._last = timestamp;
    requestAnimationFrame((ts) => this._tick(ts));
  }
}
