/*
  scrolly.js: link narrative text steps to scene states.

  Students can move through a narrative two ways, and both stay in sync:
  - Scrolling: the step crossing the middle of the viewport becomes active.
  - Next / Back buttons: scroll the target step into view and activate it.

  The section script supplies onStep(index), which must set the scene to
  that step's state from scratch (or animate to it). Making onStep depend
  only on the index is what lets Back restore a previous state exactly.
*/

import { prefersReducedMotion } from "./scene.js";

/**
 * @param {object} options
 * @param {HTMLElement[]} options.steps   step elements, in order
 * @param {(index:number) => void} options.onStep
 * @param {HTMLButtonElement} [options.prev]
 * @param {HTMLButtonElement} [options.next]
 * @param {HTMLElement} [options.status]  receives "Step 2 of 5"
 */
export function createScrolly({ steps, onStep, prev, next, status }) {
  let active = -1;

  // While a button-driven scroll is in flight, ignore the steps it passes
  // over; otherwise every intermediate state would flash by.
  let target = null;
  let targetTimer = 0;

  function activate(index) {
    if (index === active || index < 0 || index >= steps.length) return;
    active = index;
    steps.forEach((step, i) => {
      if (i === index) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    });
    if (prev) prev.disabled = index === 0;
    if (next) next.disabled = index === steps.length - 1;
    if (status) status.textContent = `Step ${index + 1} of ${steps.length}`;
    onStep(index);
  }

  function goTo(index) {
    if (index < 0 || index >= steps.length) return;
    target = index;
    window.clearTimeout(targetTimer);
    targetTimer = window.setTimeout(() => { target = null; }, 1200);
    steps[index].scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "center",
    });
    activate(index);
  }

  // A thin band across the middle of the viewport decides the active step.
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const index = steps.indexOf(entry.target);
        if (target !== null && index !== target) continue;
        if (index === target) target = null;
        activate(index);
      }
    },
    { rootMargin: "-45% 0px -45% 0px" }
  );
  steps.forEach((step) => observer.observe(step));

  prev?.addEventListener("click", () => goTo(active - 1));
  next?.addEventListener("click", () => goTo(active + 1));

  activate(0);
  return { goTo, get index() { return active; } };
}
