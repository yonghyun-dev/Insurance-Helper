import { useEffect, type RefObject } from 'react';

export function useAutoScroll<T extends HTMLElement>(
  ref: RefObject<T>,
  deps: ReadonlyArray<unknown>,
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
