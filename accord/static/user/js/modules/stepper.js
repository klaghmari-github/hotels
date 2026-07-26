/**
 * Wizard 5 etapes.
 */

import { $, $$ } from "../../../shared/js/dom.js";

export class Stepper {
  /**
   * @param {object} opts
   * @param {number} [opts.maxStep]
   * @param {(step: number) => void} [opts.onEnter]
   */
  constructor({ maxStep = 5, onEnter } = {}) {
    this.step = 1;
    this.maxStep = maxStep;
    this.onEnter = onEnter || (() => {});
  }

  setStep(n) {
    this.step = Math.min(Math.max(n, 1), this.maxStep);
    $$(".panel").forEach((p) => {
      p.classList.toggle("hidden", Number(p.dataset.panel) !== this.step);
    });
    $$(".step").forEach((s) => {
      const i = Number(s.dataset.step);
      s.classList.toggle("active", i === this.step);
      s.classList.toggle("done", i < this.step);
    });
    const prev = $("#btn-prev");
    const next = $("#btn-next");
    const label = $("#step-label");
    if (prev) prev.disabled = this.step === 1;
    if (next) {
      next.textContent = this.step === this.maxStep ? "Relancer" : "Valider";
    }
    if (label) label.textContent = `Étape ${this.step} / ${this.maxStep}`;
    this.onEnter(this.step);
  }

  wire() {
    $("#btn-prev")?.addEventListener("click", () => this.setStep(this.step - 1));
    $$(".step").forEach((s) => {
      const go = () => this.setStep(Number(s.dataset.step));
      s.addEventListener("click", go);
      s.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          go();
        }
      });
    });
  }
}
