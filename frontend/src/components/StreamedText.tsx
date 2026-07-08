// 답변 텍스트를 타이핑처럼 순차 노출(클라이언트 스트리밍 효과).
// 구조화 응답(인용 강제)은 백엔드 토큰 스트리밍이 어려우므로, 완성된 텍스트를 프론트에서
// 점진 노출한다. 메시지별로 최초 1회만 애니메이션하고 이후 재렌더에는 전체를 즉시 표시.
import { useEffect, useRef, useState } from 'react';
import Markdown from './Markdown';

interface Props {
  text: string;
  speed?: number; // 틱 간격(ms)
  onTick?: () => void; // 노출 진행 시 콜백(예: 스크롤 하단 유지)
  markdown?: boolean; // 완료 시 마크다운으로 렌더(스트리밍 중엔 평문, 부분 md 깨짐 방지)
}

export default function StreamedText({ text, speed = 16, onTick, markdown = false }: Props) {
  const [count, setCount] = useState(0);
  const doneRef = useRef(false);

  useEffect(() => {
    if (doneRef.current || !text) {
      setCount(text.length);
      return;
    }
    // 길이에 따라 틱당 노출 글자수를 조절해 전체 소요시간을 ~1.5~2.5초로 유지.
    const step = Math.min(4, Math.max(1, Math.ceil(text.length / 120)));
    let n = 0;
    const id = window.setInterval(() => {
      n += step;
      if (n >= text.length) {
        n = text.length;
        window.clearInterval(id);
        doneRef.current = true;
      }
      setCount(n);
      onTick?.();
    }, speed);
    return () => window.clearInterval(id);
    // text 는 메시지당 고정(재렌더로 바뀌지 않음) — 최초 마운트 시 1회 애니메이션.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, speed]);

  // 스트리밍 완료 후엔 마크다운으로 렌더(표·목록·볼드). 진행 중엔 평문 슬라이스.
  const done = count >= text.length;
  if (markdown && done) {
    return <Markdown>{text}</Markdown>;
  }
  return <>{text.slice(0, count)}</>;
}
