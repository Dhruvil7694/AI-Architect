"use client";

import type { ViewTransform } from "@/geometry/transform";

const FEET_TO_METRES = 0.3048;

interface ScaleBarProps {
  viewTransform: ViewTransform;
}

export function ScaleBar({ viewTransform }: ScaleBarProps) {
  const { scale } = viewTransform;

  // Target on-screen length in pixels for the main segment.
  const targetPx = 100;

  // Compute metres per pixel from DXF feet scale.
  const metresPerPixel = FEET_TO_METRES / scale;
  const rawMetres = targetPx * metresPerPixel;

  // Round to a nice value (1, 2, 5 x 10^n).
  const nice = niceDistance(rawMetres);
  const barPx = nice / metresPerPixel;

  const y = 560; // near bottom (viewBox height ~600)
  const x0 = 40;
  const x1 = x0 + barPx;

  const mid1 = x0 + (x1 - x0) / 2;

  return (
    <g
      transform={`translate(0, 0)`}
      aria-hidden="true"
    >
      {/* Base line */}
      <line
        x1={x0}
        y1={y}
        x2={x1}
        y2={y}
        stroke="#111827"
        strokeWidth={1}
      />
      {/* Ticks: 0, mid, end */}
      {[x0, mid1, x1].map((x, i) => (
        <line
          // eslint-disable-next-line react/no-array-index-key
          key={i}
          x1={x}
          y1={y - 4}
          x2={x}
          y2={y + 4}
          stroke="#111827"
          strokeWidth={1}
        />
      ))}

      {/* Labels */}
      <text x={x0} y={y + 14} fontSize={9} fill="#4b5563" textAnchor="middle">
        0 m
      </text>
      <text x={mid1} y={y + 14} fontSize={9} fill="#4b5563" textAnchor="middle">
        {(nice / 2).toFixed(0)} m
      </text>
      <text x={x1} y={y + 14} fontSize={9} fill="#4b5563" textAnchor="middle">
        {nice.toFixed(0)} m
      </text>
    </g>
  );
}

function niceDistance(d: number): number {
  if (d <= 0) return 10;
  const exp = Math.floor(Math.log10(d));
  const base = Math.pow(10, exp);
  const n = d / base;
  if (n < 1.5) return 1 * base;
  if (n < 3.5) return 2 * base;
  if (n < 7.5) return 5 * base;
  return 10 * base;
}

