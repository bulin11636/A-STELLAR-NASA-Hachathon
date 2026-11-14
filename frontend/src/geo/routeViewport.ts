export type Viewport = { x: number; y: number; width: number; height: number };

export function fitRoute(points: number[][], minimumSpan: number): Viewport {
  let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
  for (const [x,y] of points) { left = Math.min(left,x); right = Math.max(right,x); top = Math.min(top,y); bottom = Math.max(bottom,y); }
  const width = Math.max(minimumSpan, (right - left) * 1.3);
  const height = Math.max(minimumSpan, (bottom - top) * 1.3);
  // The preview has a square viewport; preserve metric aspect ratio.
  const span = Math.max(width, height);
  return { x: (left + right - span) / 2, y: (top + bottom - span) / 2, width: span, height: span };
}

export function zoomViewport(view: Viewport, factor: number, minimumSpan: number, maximumSpan: number): Viewport {
  const span = Math.min(maximumSpan, Math.max(minimumSpan, view.width * factor));
  return { x: view.x + (view.width - span) / 2, y: view.y + (view.height - span) / 2, width: span, height: span };
}
