import catalog from "@/lib/generated/feedback-catalog.json";
import type { FeedbackItem, Severity } from "@/types";

export const DISCLAIMER: string = catalog.disclaimer;
const CAT = catalog.catalog as Record<string, { severity: string; template: string }>;

/** Formats Python-style templates: {name}, {name:.0f}, {name:.0%}. */
export function makeFeedback(code: string, vars: Record<string, number> = {}): FeedbackItem {
  const { severity, template } = CAT[code];
  const message = template.replace(/\{(\w+)(?::\.(\d+)([f%]))?\}/g, (_m, name: string, nd?: string, kind?: string) => {
    const v = vars[name];
    if (kind === "%") return `${(v * 100).toFixed(Number(nd))}%`;
    if (kind === "f") return v.toFixed(Number(nd));
    return String(v);
  });
  return { code, severity: severity as Severity, message };
}
