// Sprint 20 — 백엔드 ISO created_at → 한국어 시:분 표기 ("오후 2:31").
// 기존 frontend 에는 시각 표시 헬퍼가 없어 신규 작성 (MessageBubble.time 필수).

export function koTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('ko-KR', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}
