import { useEffect } from 'react';

/**
 * Warn users before they navigate away or close the tab when there are unsaved
 * changes. Registers a `beforeunload` listener that triggers the browser's
 * native "Leave site?" dialog whenever `isDirty` is true.
 *
 * @example
 *   const isDirty = saveStatus === 'unsaved';
 *   useUnsavedChangesWarning(isDirty);
 */
export function useUnsavedChangesWarning(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return;

    const handler = (event: BeforeUnloadEvent) => {
      // Modern browsers ignore custom messages, but preventDefault + returnValue
      // is required to trigger the native "Leave site?" dialog.
      event.preventDefault();
      event.returnValue = '';
    };

    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);
}
