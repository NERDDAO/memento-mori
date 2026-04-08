// client/src/ui/sprite-renderer.ts
/**
 * Pixel sprite renderer for canvas contexts.
 * Decodes base64 PNG sprites and draws them with nearest-neighbor scaling
 * for crisp 8-bit aesthetic.
 */

/** Cache decoded Image elements by their base64 content. */
const spriteCache = new Map<string, HTMLImageElement>();

/**
 * Get or create a cached Image element from a base64 PNG string.
 */
function getOrLoadImage(spriteB64: string): HTMLImageElement | null {
  const cached = spriteCache.get(spriteB64);
  if (cached && cached.complete) return cached;
  if (cached) return null; // still loading

  const img = new Image();
  img.src = `data:image/png;base64,${spriteB64}`;
  spriteCache.set(spriteB64, img);

  // Return null on first call; image will be ready on next paint
  return img.complete ? img : null;
}

/**
 * Draw a pixel sprite onto a canvas context at a given pixel position.
 * Uses nearest-neighbor scaling for crisp pixel art.
 *
 * @returns Height consumed in pixels, or 0 if image not yet loaded
 */
export function drawSprite(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  spriteB64: string,
  scale: number = 2,
): number {
  const img = getOrLoadImage(spriteB64);
  if (!img) return 0;

  const w = img.naturalWidth * scale;
  const h = img.naturalHeight * scale;

  // Nearest-neighbor scaling for pixel art
  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;

  return h;
}

/**
 * Draw a pixel sprite centered within a given region width.
 */
export function drawSpriteCentered(
  ctx: CanvasRenderingContext2D,
  regionX: number,
  regionWidth: number,
  y: number,
  spriteB64: string,
  scale: number = 2,
): number {
  const img = getOrLoadImage(spriteB64);
  if (!img) return 0;

  const w = img.naturalWidth * scale;
  const h = img.naturalHeight * scale;
  const x = regionX + Math.floor((regionWidth - w) / 2);

  const prevSmoothing = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, x, y, w, h);
  ctx.imageSmoothingEnabled = prevSmoothing;

  return h;
}

/**
 * Clear the sprite cache. Call when navigating away or on memory pressure.
 */
export function clearSpriteCache(): void {
  spriteCache.clear();
}
