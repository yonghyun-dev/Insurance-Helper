// 글자 크기 토글 — 소/중/대. localStorage 영속 + <html> 클래스(fs--*) 적용으로
// 앱 전역에 반영된다. (접근성: WCAG 2.1 — 텍스트 크기 조절)
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type FontSize = 'small' | 'medium' | 'large';

const FONT_SIZE_STORAGE_KEY = 'ica_font_size';

function readInitial(): FontSize {
  try {
    const v = localStorage.getItem(FONT_SIZE_STORAGE_KEY);
    if (v === 'small' || v === 'medium' || v === 'large') return v;
  } catch {
    /* SSR / storage 비활성 환경 */
  }
  return 'medium';
}

function applyToDom(size: FontSize) {
  const html = document.documentElement;
  html.classList.remove('fs--small', 'fs--medium', 'fs--large');
  html.classList.add(`fs--${size}`);
}

interface FontSizeValue {
  size: FontSize;
  setSize: (next: FontSize) => void;
}

const FontSizeContext = createContext<FontSizeValue | null>(null);

export function FontSizeProvider({ children }: { children: ReactNode }) {
  const [size, setSizeState] = useState<FontSize>(() => readInitial());

  useEffect(() => {
    applyToDom(size);
    try {
      localStorage.setItem(FONT_SIZE_STORAGE_KEY, size);
    } catch {
      /* noop */
    }
  }, [size]);

  const setSize = useCallback((next: FontSize) => setSizeState(next), []);
  const value = useMemo(() => ({ size, setSize }), [size, setSize]);

  return <FontSizeContext.Provider value={value}>{children}</FontSizeContext.Provider>;
}

export function useFontSize(): FontSizeValue {
  const ctx = useContext(FontSizeContext);
  if (!ctx) throw new Error('useFontSize must be used within FontSizeProvider');
  return ctx;
}
