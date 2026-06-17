import { useEffect, useRef, useState } from 'react';

export interface StreamingOptions {
  charDelayMs?: number;
  startDelayMs?: number;
  enabled?: boolean;
}

export interface StreamingResult {
  text: string;
  done: boolean;
  streaming: boolean;
}

export function useStreamingText(
  fullText: string,
  { charDelayMs = 18, startDelayMs = 0, enabled = true }: StreamingOptions = {},
): StreamingResult {
  const [text, setText] = useState(enabled ? '' : fullText);
  const [streaming, setStreaming] = useState(enabled);
  const indexRef = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setText(fullText);
      setStreaming(false);
      return;
    }

    indexRef.current = 0;
    setText('');
    setStreaming(true);

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    function tick() {
      if (cancelled) return;
      indexRef.current += 1;
      if (indexRef.current >= fullText.length) {
        setText(fullText);
        setStreaming(false);
        return;
      }
      setText(fullText.slice(0, indexRef.current));
      timer = setTimeout(tick, charDelayMs);
    }

    const startTimer = setTimeout(tick, startDelayMs);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      clearTimeout(timer);
    };
  }, [fullText, charDelayMs, startDelayMs, enabled]);

  return { text, done: !streaming, streaming };
}
