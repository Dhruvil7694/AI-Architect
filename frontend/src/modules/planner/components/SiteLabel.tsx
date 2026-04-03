"use client";

/**
 * SiteLabel — SVG label with a rounded white background and drop shadow.
 *
 * Rendered inside the SVG canvas (not as an HTML overlay) so it participates
 * in the SVG coordinate space and can be exported as part of the drawing.
 *
 * Usage:
 *   <SiteLabel x={cx} y={cy} primary="T1" secondary="12 fl · 850 m²" />
 */

interface SiteLabelProps {
  x: number;
  y: number;
  primary: string;
  secondary?: string;
  color?: string; // accent dot color (defaults to none)
}

const PAD_X = 6;
const PAD_Y = 4;
const LINE_H = 13;
const FONT_PX_PER_CHAR = 5.5; // rough character width estimate

export function SiteLabel({ x, y, primary, secondary, color }: SiteLabelProps) {
  const maxLen = Math.max(primary.length, secondary?.length ?? 0);
  const rectW  = maxLen * FONT_PX_PER_CHAR + PAD_X * 2 + (color ? 10 : 0);
  const lines  = secondary ? 2 : 1;
  const rectH  = lines * LINE_H + PAD_Y * 2;
  const rx     = x - rectW / 2;
  const ry     = y - rectH / 2;

  return (
    <g
      style={{ pointerEvents: "none" }}
      filter="drop-shadow(0 1px 3px rgba(0,0,0,0.18))"
    >
      <rect
        x={rx}
        y={ry}
        width={rectW}
        height={rectH}
        rx={3}
        fill="white"
        fillOpacity={0.93}
      />
      {/* Accent dot (e.g. tower colour) */}
      {color && (
        <circle
          cx={rx + 8}
          cy={y}
          r={3}
          fill={color}
        />
      )}
      <text
        x={color ? rx + 16 : x}
        y={secondary ? y - LINE_H / 2 + PAD_Y / 2 : y}
        textAnchor={color ? "start" : "middle"}
        dominantBaseline="middle"
        fontSize={10}
        fontWeight="600"
        fill="#1e293b"
        fontFamily="system-ui, sans-serif"
      >
        {primary}
      </text>
      {secondary && (
        <text
          x={color ? rx + 16 : x}
          y={y + LINE_H / 2 + PAD_Y / 2}
          textAnchor={color ? "start" : "middle"}
          dominantBaseline="middle"
          fontSize={8}
          fill="#64748b"
          fontFamily="system-ui, sans-serif"
        >
          {secondary}
        </text>
      )}
    </g>
  );
}
