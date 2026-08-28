/**
 * Canvas annotation management Hook
 * provides annotation CRUD and coordinate convert capability
 */
import { useState, useCallback } from 'react';

/** annotation item type — kept in sync with GafCanvasOverlay.AnnotationType */
type AnnotationType = 'rect' | 'arrow' | 'text' | 'circle' | 'match' | 'ocr';

/** single record annotation data */
interface Annotation {
  id: string;
  type: AnnotationType;
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  label?: string;
}

/** useCanvasAnnotation Hook return value type */
interface UseCanvasAnnotationResult {
  annotations: Annotation[];
  addAnnotation: (ann: Omit<Annotation, 'id'> & { id?: string }) => void;
  updateAnnotation: (id: string, updates: Partial<Annotation>) => void;
  removeAnnotation: (id: string) => void;
  clearAnnotations: () => void;
  selectedAnnotation: Annotation | null;
  selectAnnotation: (id: string | null) => void;
}

/**
 * manage Canvas annotation CRUD
 */
export function useCanvasAnnotation(): UseCanvasAnnotationResult {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  /** add new annotation */
  const addAnnotation = useCallback((ann: Omit<Annotation, 'id'> & { id?: string }) => {
    const newAnn: Annotation = {
      ...ann,
      id: `ann_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    };
    setAnnotations((prev) => [...prev, newAnn]);
  }, []);

  /** update specified annotation */
  const updateAnnotation = useCallback((id: string, updates: Partial<Annotation>) => {
    setAnnotations((prev) => prev.map((ann) => (ann.id === id ? { ...ann, ...updates } : ann)));
  }, []);

  /** delete specified annotation */
  const removeAnnotation = useCallback((id: string) => {
    setAnnotations((prev) => prev.filter((ann) => ann.id !== id));
    setSelectedId((prev) => (prev === id ? null : prev));
  }, []);

  /** clear has annotation */
  const clearAnnotations = useCallback(() => {
    setAnnotations([]);
    setSelectedId(null);
  }, []);

  /** select in annotation */
  const selectAnnotation = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  const selectedAnnotation = annotations.find((ann) => ann.id === selectedId) ?? null;

  return {
    annotations,
    addAnnotation,
    updateAnnotation,
    removeAnnotation,
    clearAnnotations,
    selectedAnnotation,
    selectAnnotation,
  };
}
