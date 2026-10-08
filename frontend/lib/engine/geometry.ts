// Port of backend/app/vision/geometry.py + smoothing.py (parity-tested against the Python engine).
export type V2 = [number, number];
const EPS = 1e-9;

export const distance = (a: V2, b: V2) => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function angleDeg(a: V2, b: V2, c: V2): number {
  const ba: V2 = [a[0] - b[0], a[1] - b[1]];
  const bc: V2 = [c[0] - b[0], c[1] - b[1]];
  const na = Math.hypot(...ba), nc = Math.hypot(...bc);
  if (!(na >= EPS) || !(nc >= EPS) || !isFinite(na) || !isFinite(nc)) return NaN;
  const cos = (ba[0] * bc[0] + ba[1] * bc[1]) / (na * nc);
  return (Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI;
}

export function torsoInclinationDeg(shoulder: V2, hip: V2): number {
  const v: V2 = [shoulder[0] - hip[0], shoulder[1] - hip[1]];
  const n = Math.hypot(...v);
  if (n < EPS) return NaN;
  return (Math.acos(Math.max(-1, Math.min(1, -v[1] / n))) * 180) / Math.PI;
}

export function lineDeviation(p: V2, a: V2, b: V2): number {
  const d: V2 = [b[0] - a[0], b[1] - a[1]];
  const length = Math.hypot(...d);
  if (length < EPS || Math.abs(d[0]) < 0.2 * length) return NaN;
  const lineY = a[1] + ((p[0] - a[0]) * d[1]) / d[0];
  const cross = Math.abs(d[0] * (p[1] - a[1]) - d[1] * (p[0] - a[0])) / length;
  const v = cross / length;
  return p[1] - lineY < 0 ? -v : v;
}

export function lineAngleFromHorizontalDeg(a: V2, b: V2): number {
  const d: V2 = [b[0] - a[0], b[1] - a[1]];
  if (Math.hypot(...d) < EPS) return NaN;
  return (Math.atan2(Math.abs(d[1]), Math.abs(d[0])) * 180) / Math.PI;
}

export function weightedMean(values: number[], weights: number[]): number {
  let s = 0, w = 0;
  values.forEach((v, i) => {
    const wi = weights[i];
    if (isFinite(v) && isFinite(wi) && wi > 0) { s += v * wi; w += wi; }
  });
  return w > 0 ? s / w : NaN;
}

export const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
export function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

export function emaAlpha(dtMs: number, tauMs: number): number {
  if (tauMs <= 0 || dtMs <= 0) return 1;
  return 1 - Math.exp(-dtMs / tauMs);
}

/** Pose in normalized image coordinates; use xy() for aspect-corrected 2D points. */
export interface Pose { x: number[]; y: number[]; vis: number[]; t: number; aspect: number }
export const xy = (p: Pose, i: number): V2 => [p.x[i] * p.aspect, p.y[i]];
export const minVis = (p: Pose, ...idx: number[]) => Math.min(...idx.map((i) => p.vis[i]));

export class LandmarkSmoother {
  private x: number[] | null = null;
  private y: number[] | null = null;
  private t: number | null = null;
  constructor(public tauMs = 60, public resetGapMs = 500) {}
  reset() { this.x = this.y = null; this.t = null; }
  update(p: Pose): Pose {
    if (!this.x || !this.y || this.t === null || p.t < this.t || p.t - this.t > this.resetGapMs || this.tauMs <= 0) {
      this.x = [...p.x]; this.y = [...p.y];
    } else {
      const a = emaAlpha(p.t - this.t, this.tauMs);
      this.x = this.x.map((v, i) => v + a * (p.x[i] - v));
      this.y = this.y.map((v, i) => v + a * (p.y[i] - v));
    }
    this.t = p.t;
    return { ...p, x: [...this.x], y: [...this.y] };
  }
}
