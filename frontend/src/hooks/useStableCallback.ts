import { useRef } from 'react';

/**
 * Keep a ref to the latest callback without triggering re-renders or effect re-runs.
 *
 * This is useful when a hook accepts a callback that may change on every render
 * (e.g. inline arrow function passed by the parent) but the effect that uses it
 * should only re-run when other dependencies change (e.g. message type, url).
 *
 * The returned ref's `.current` is always up-to-date with the latest callback,
 * updated synchronously during render (safe because refs are mutable and the
 * mutation does not trigger re-render).
 *
 * Related: TD-052 — extracts the shared "stable handler ref" pattern previously
 * duplicated in useWebSocket / useNotificationWebSocket / useLogStream.
 *
 * @example
 * ```ts
 * function useFoo(type: string, onFoo: (data: unknown) => void) {
 *   const onFooRef = useStableCallback(onFoo);
 *   useEffect(() => {
 *     const stable = (data: unknown) => onFooRef.current(data);
 *     subscribe(type, stable);
 *     return () => unsubscribe(type, stable);
 *   }, [type]);
 * }
 * ```
 */
export function useStableCallback<T extends (...args: never[]) => unknown>(callback: T): React.MutableRefObject<T> {
  const ref = useRef<T>(callback);
  ref.current = callback;
  return ref;
}
