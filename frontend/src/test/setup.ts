import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library auto-cleans only when vitest `globals` is on, and it is not.
// Without this every `render` in a file accumulates in the document, so a
// second render of the same component makes `getByRole` ambiguous and the
// failure reads as a bug in the component rather than in the harness.
afterEach(cleanup);

class TestIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];

  constructor(private readonly callback: IntersectionObserverCallback) {}

  disconnect() {}

  observe(target: Element) {
    const rect = target.getBoundingClientRect();
    this.callback([
      {
        boundingClientRect: rect,
        intersectionRatio: 1,
        intersectionRect: rect,
        isIntersecting: true,
        rootBounds: null,
        target,
        time: 0,
      },
    ], this);
  }

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  unobserve() {}
}

Object.defineProperty(window, "IntersectionObserver", {
  configurable: true,
  writable: true,
  value: TestIntersectionObserver,
});
