/**
 * coordinate picker Hook
 * used for in Canvas or screenshot above get current mouse / touch coordinate
 */
import { useState, useCallback } from 'react';

/** coordinate point */
interface CoordinatePoint {
  x: number;
  y: number;
}

/** useCoordinatePicker Hook return value type */
interface UseCoordinatePickerResult {
  coordinates: CoordinatePoint | null;
  pickCoordinate: (x: number, y: number) => void;
  clearCoordinate: () => void;
  isPicking: boolean;
  startPicking: () => void;
  stopPicking: () => void;
}

/**
 * management coordinate pick status
 * used for screenshot above coordinate select operation
 */
export function useCoordinatePicker(): UseCoordinatePickerResult {
  const [coordinates, setCoordinates] = useState<CoordinatePoint | null>(null);
  const [isPicking, setIsPicking] = useState(false);

  /** pick specified coordinate */
  const pickCoordinate = useCallback((x: number, y: number) => {
    setCoordinates({ x, y });
    setIsPicking(false);
  }, []);

  /** clear current coordinate */
  const clearCoordinate = useCallback(() => {
    setCoordinates(null);
  }, []);

  /** start coordinate pick mode */
  const startPicking = useCallback(() => {
    setIsPicking(true);
    setCoordinates(null);
  }, []);

  /** stop coordinate pick mode */
  const stopPicking = useCallback(() => {
    setIsPicking(false);
  }, []);

  return {
    coordinates,
    pickCoordinate,
    clearCoordinate,
    isPicking,
    startPicking,
    stopPicking,
  };
}
