"use client";

interface NorthArrowProps {
  rotationDeg?: number;
}

export function NorthArrow({ rotationDeg = 0 }: NorthArrowProps) {
  const x = 760;
  const y = 60;

  // The site content is rotated by rotationDeg inside SitePlanLayers.
  // To keep the arrow pointing to geographic north on screen, rotate it
  // in the opposite direction.
  const arrowRotation = -rotationDeg;

  return (
    <g
      transform={`translate(${x}, ${y}) rotate(${arrowRotation})`}
      aria-label="North"
    >
      {/* Shaft */}
      <line
        x1={0}
        y1={12}
        x2={0}
        y2={-12}
        stroke="#111827"
        strokeWidth={1.5}
      />
      {/* Triangle head */}
      <polygon
        points="0,-20 -6,-8 6,-8"
        fill="#111827"
      />
      {/* N label (not rotated) */}
      <g transform={`rotate(${rotationDeg})`}>
        <text
          x={0}
          y={22}
          textAnchor="middle"
          fontSize={10}
          fontWeight={600}
          fill="#111827"
        >
          N
        </text>
      </g>
    </g>
  );
}

