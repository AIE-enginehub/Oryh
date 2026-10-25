import { describe, expect, it } from "vitest";

import base from "./data-catalog.json";
import labels from "../locales/zh-CN/data-catalog.json";
import { dataCatalog, findResource } from "./dataCatalog";

describe("generated bilingual catalog", () => {
  it("retains English labels and restores every Chinese label by stable ID", () => {
    expect(dataCatalog.groups.map((group) => group.label)).toEqual(
      base.groups.map((group) => [labels.groups[group.key as keyof typeof labels.groups], group.label[1]]),
    );
    for (const resource of base.resources) {
      const localized = labels.resources[resource.key as keyof typeof labels.resources];
      const actual = findResource(resource.key)!;
      expect(actual.path).toBe(resource.path);
      expect(actual.label).toEqual([localized.label, resource.label[1]]);
      for (const related of actual.related ?? []) {
        const key = `${related.resource}:${related.param}`;
        expect(related.label[0]).toBe((localized.related as Record<string, string>)[key]);
      }
    }
  });
});
