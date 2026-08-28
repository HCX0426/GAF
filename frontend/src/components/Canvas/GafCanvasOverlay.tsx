/**
 * Canvas overlay component with debug visualization
 * Renders annotation layer on device screenshots, supports match results,
 * confidence scores, crosshair cursor, and coordinate display
 *
 * Display scaling: uses CSS `object-fit: contain` so the canvas backing store
 * (set to the image's natural dimensions) is letterboxed within the CSS box.
 * Click/mouse coordinates are mapped through the letterbox offsets so device
 * input targets the correct pixel even when the image is scaled.
 */
import { useRef, useEffect, useState, useCallback, type CSSProperties } from 'react';

/** Annotation type enum */
export type AnnotationType = 'rect' | 'arrow' | 'text' | 'circle' | 'match' | 'ocr';

/** Single annotation data */
export interface Annotation {
  id: string;
  type: AnnotationType;
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  label?: string;
  confidence?: number;
}

/** Debug info displayed on canvas overlay */
export interface DebugInfo {
  fps?: number;
  screenshotLatencyMs?: number;
  inputLatencyMs?: number;
  currentStep?: string;
  deviceName?: string;
  resolution?: string;
}

/** GafCanvasOverlay component props */
interface GafCanvasOverlayProps {
  /** Fallback canvas width (overridden by image natural width once loaded) */
  width: number;
  /** Fallback canvas height (overridden by image natural height once loaded) */
  height: number;
  annotations: Annotation[];
  imageBase64?: string;
  /** Direct image URL (takes precedence over imageBase64 when both are provided). */
  imageUrl?: string;
  style?: CSSProperties;
  className?: string;
  onCanvasClick?: (x: number, y: number) => void;
  onCanvasMove?: (x: number, y: number) => void;
  showCrosshair?: boolean;
  showDebugInfo?: boolean;
  debugInfo?: DebugInfo;
  showConfidence?: boolean;
}

/** Detect MIME type from base64 header: JPEG starts with /9j/, PNG with iVBOR */
function detectMime(b64: string): string {
  return b64.startsWith('/9j/') ? 'image/jpeg' : 'image/png';
}

/**
 * Canvas screenshot overlay with debug visualization
 * Supports rect/arrow/text/circle/match/ocr annotations,
 * crosshair cursor, confidence labels, and debug stats panel
 */
export function GafCanvasOverlay({
  width: widthProp,
  height: heightProp,
  annotations,
  imageBase64,
  imageUrl,
  style,
  className,
  onCanvasClick,
  onCanvasMove,
  showCrosshair = false,
  showDebugInfo = false,
  debugInfo,
  showConfidence = true,
}: GafCanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  /** Cached loaded HTMLImageElement to avoid re-decoding on every redraw */
  const imgRef = useRef<HTMLImageElement | null>(null);
  /** Last image base64 to detect changes */
  const lastImageRef = useRef<string | undefined>(undefined);
  /** Actual image dimensions from naturalWidth/naturalHeight.
   *  Falls back to widthProp/heightProp until the image loads. This ensures
   *  the canvas backing store always matches the real image, even if the
   *  caller's width/height props are stale or mismatched. */
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  /** Bump on every successful image load so the draw effect re-runs even when
   *  natural dimensions are unchanged between consecutive frames. */
  const [imgVersion, setImgVersion] = useState(0);

  const width = naturalSize?.w || widthProp;
  const height = naturalSize?.h || heightProp;

  /** Load (and cache) the image whenever imageBase64 / imageUrl changes.
   *  R37-P1 C5: imageUrl takes precedence over imageBase64. Updates
   *  naturalSize + imgVersion so downstream draw effect re-runs. */
  useEffect(() => {
    // R37-P1 C5: prefer imageUrl (direct URL) over imageBase64 (raw base64).
    const imageKey = imageUrl || imageBase64;
    if (!imageKey) {
      imgRef.current = null;
      lastImageRef.current = undefined;
      return;
    }
    if (lastImageRef.current === imageKey && imgRef.current) {
      return;
    }
    lastImageRef.current = imageKey;
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      setImgVersion((v) => v + 1);
      if (img.naturalWidth && img.naturalHeight) {
        setNaturalSize((prev) => {
          if (prev?.w === img.naturalWidth && prev?.h === img.naturalHeight) {
            return prev;
          }
          return { w: img.naturalWidth, h: img.naturalHeight };
        });
      }
    };
    img.onerror = () => {
      imgRef.current = null;
      console.warn('[GafCanvasOverlay] Failed to load image:', imageUrl || `base64 len=${imageBase64?.length}`);
    };
    img.src = imageUrl || `data:${detectMime(imageBase64!)};base64,${imageBase64}`;
  }, [imageBase64, imageUrl]);

  /** Draw image + annotations + crosshair + debug panel. Re-runs on any
   *  relevant change including image load (imgVersion) and dimension updates. */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Sync canvas backing store with actual dimensions
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);

    if (imgRef.current && width > 0 && height > 0) {
      ctx.drawImage(imgRef.current, 0, 0, width, height);
    } else if (imageBase64 || imageUrl) {
      // Image not loaded yet — show placeholder background
      ctx.fillStyle = '#1a1a2e';
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = '#666';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('截图加载中...', width / 2, height / 2);
    }

    drawAnnotations(ctx, annotations, showConfidence);
    if (mousePos && showCrosshair) {
      drawCrosshair(ctx, mousePos.x, mousePos.y, width, height);
    }
    if (showDebugInfo && debugInfo) {
      drawDebugPanel(ctx, debugInfo);
    }
  }, [
    width,
    height,
    imageBase64,
    imageUrl,
    imgVersion,
    annotations,
    mousePos,
    showCrosshair,
    showDebugInfo,
    debugInfo,
    showConfidence,
  ]);

  /**
   * Map a mouse event to image pixel coordinates, accounting for CSS
   * `object-fit: contain` letterboxing. The canvas display box (getBoundingClientRect)
   * may differ in aspect ratio from the canvas backing store, so the image is
   * centered with black bars on two sides. This function computes the actual
   * image display rectangle and maps the click into backing-store pixel space,
   * clamping to [0, width] / [0, height] so clicks in the letterbox region
   * map to the nearest image edge instead of producing out-of-range coords.
   */
  const mapEventToImageCoords = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>): { x: number; y: number } => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      if (width <= 0 || height <= 0 || rect.width <= 0 || rect.height <= 0) {
        return { x: 0, y: 0 };
      }
      const canvasAspect = width / height;
      const rectAspect = rect.width / rect.height;
      let imgX = 0,
        imgY = 0,
        imgW = rect.width,
        imgH = rect.height;
      if (canvasAspect > rectAspect) {
        // Image wider than display box → letterbox top & bottom
        imgH = rect.width / canvasAspect;
        imgY = (rect.height - imgH) / 2;
      } else {
        // Image taller than display box → letterbox left & right
        imgW = rect.height * canvasAspect;
        imgX = (rect.width - imgW) / 2;
      }
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;
      const px = ((clickX - imgX) / imgW) * width;
      const py = ((clickY - imgY) / imgH) * height;
      return {
        x: Math.max(0, Math.min(width, px)),
        y: Math.max(0, Math.min(height, py)),
      };
    },
    [width, height],
  );

  /** Handle click event, calculate relative coordinates */
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!onCanvasClick) return;
      const { x, y } = mapEventToImageCoords(e);
      onCanvasClick(x, y);
    },
    [onCanvasClick, mapEventToImageCoords],
  );

  /** Handle mouse move for crosshair tracking */
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const { x, y } = mapEventToImageCoords(e);
      setMousePos({ x, y });
      onCanvasMove?.(x, y);
    },
    [mapEventToImageCoords, onCanvasMove],
  );

  const handleMouseLeave = useCallback(() => {
    setMousePos(null);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{
        display: 'block',
        objectFit: 'contain',
        objectPosition: 'center center',
        border: '1px solid #d9d9d9',
        borderRadius: 4,
        ...style,
      }}
      className={className}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    />
  );
}

/** Draw all annotations on canvas context */
function drawAnnotations(ctx: CanvasRenderingContext2D, annotations: Annotation[], showConfidence: boolean): void {
  annotations.forEach((ann) => {
    const isMatch = ann.type === 'match';
    const isOcr = ann.type === 'ocr';

    if (isMatch || isOcr) {
      const conf = ann.confidence ?? 1.0;
      if (conf >= 0.8) {
        ctx.strokeStyle = '#00ff00';
        ctx.fillStyle = 'rgba(0, 255, 0, 0.15)';
      } else if (conf >= 0.5) {
        ctx.strokeStyle = '#faad14';
        ctx.fillStyle = 'rgba(250, 173, 20, 0.15)';
      } else {
        ctx.strokeStyle = '#ff4d4f';
        ctx.fillStyle = 'rgba(255, 77, 79, 0.15)';
      }
      ctx.lineWidth = 2;
      ctx.fillRect(ann.x, ann.y, ann.width, ann.height);
      ctx.strokeRect(ann.x, ann.y, ann.width, ann.height);

      if (showConfidence && ann.label) {
        ctx.font = 'bold 12px monospace';
        ctx.fillStyle = ctx.strokeStyle;
        const text = `${ann.label} (${(conf * 100).toFixed(0)}%)`;
        const textWidth = ctx.measureText(text).width;
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(ann.x, ann.y - 16, textWidth + 6, 16);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.fillText(text, ann.x + 3, ann.y - 4);
      }
      return;
    }

    ctx.strokeStyle = ann.color;
    ctx.fillStyle = ann.color;
    ctx.lineWidth = 2;

    switch (ann.type) {
      case 'rect':
        ctx.strokeRect(ann.x, ann.y, ann.width, ann.height);
        break;
      case 'circle':
        ctx.beginPath();
        ctx.ellipse(ann.x + ann.width / 2, ann.y + ann.height / 2, ann.width / 2, ann.height / 2, 0, 0, Math.PI * 2);
        ctx.stroke();
        break;
      case 'arrow':
        drawArrow(ctx, ann.x, ann.y, ann.x + ann.width, ann.y + ann.height);
        break;
      case 'text':
        if (ann.label) {
          ctx.font = '14px sans-serif';
          ctx.fillText(ann.label, ann.x, ann.y);
        }
        break;
    }
  });
}

/** Draw arrow from (x1,y1) to (x2,y2) with arrowhead */
function drawArrow(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number): void {
  const headLen = 10;
  const angle = Math.atan2(y2 - y1, x2 - x1);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
}

/** Draw crosshair cursor at position */
function drawCrosshair(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): void {
  const gap = 8;
  const len = 16;

  ctx.strokeStyle = '#ff0000';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 2]);

  ctx.beginPath();
  ctx.moveTo(Math.max(0, x - len), y);
  ctx.lineTo(Math.max(0, x - gap), y);
  ctx.moveTo(Math.min(x + gap, w), y);
  ctx.lineTo(Math.min(w, x + len), y);
  ctx.moveTo(x, Math.max(0, y - len));
  ctx.lineTo(x, Math.max(0, y - gap));
  ctx.moveTo(x, Math.min(y + gap, h));
  ctx.lineTo(Math.min(h, y + len), y);
  ctx.stroke();

  ctx.setLineDash([]);

  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(x, y, 6, 0, Math.PI * 2);
  ctx.stroke();

  ctx.fillStyle = 'rgba(255, 0, 0, 0.8)';
  ctx.font = '11px monospace';
  const coordText = `${Math.round(x)}, ${Math.round(y)}`;
  const textW = ctx.measureText(coordText).width;
  ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
  ctx.fillRect(x + 10, y - 20, textW + 8, 18);
  ctx.fillStyle = '#ff4444';
  ctx.fillText(coordText, x + 14, y - 6);
}

/** Draw debug info panel in top-left corner */
function drawDebugPanel(ctx: CanvasRenderingContext2D, info: DebugInfo): void {
  const lines: string[] = [];
  if (info.deviceName) lines.push(`Device: ${info.deviceName}`);
  if (info.resolution) lines.push(`Res: ${info.resolution}`);
  if (info.fps != null) lines.push(`FPS: ${info.fps.toFixed(1)}`);
  if (info.screenshotLatencyMs != null) lines.push(`Screen: ${info.screenshotLatencyMs.toFixed(0)}ms`);
  if (info.inputLatencyMs != null) lines.push(`Input: ${info.inputLatencyMs.toFixed(0)}ms`);
  if (info.currentStep) lines.push(`Step: ${info.currentStep}`);

  if (lines.length === 0) return;

  const padding = 8;
  const lineHeight = 16;
  const panelW = 180;
  const panelH = lines.length * lineHeight + padding * 2;

  ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
  ctx.fillRect(4, 4, panelW, panelH);
  ctx.strokeStyle = '#444';
  ctx.lineWidth = 1;
  ctx.strokeRect(4, 4, panelW, panelH);

  ctx.font = '12px monospace';
  ctx.fillStyle = '#00ff00';
  lines.forEach((line, i) => {
    ctx.fillText(line, 4 + padding, 4 + padding + (i + 1) * lineHeight - 4);
  });
}

export default GafCanvasOverlay;
