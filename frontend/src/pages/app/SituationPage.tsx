import { useEffect, useRef, useState } from 'react';
import { Button, Icon } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import PreStepper from '../../design-system/patterns/onboarding/PreStepper';
import s from './SituationPage.module.css';

export interface SituationPageProps {
  onSubmit: (text: string) => void;
  anonymous?: boolean;   // Sprint 34 — 비로그인 표준약관 상담(스텝퍼 숨김, 카피 변경)
}

export default function SituationPage({ onSubmit, anonymous = false }: SituationPageProps) {
  const [text, setText] = useState('');
  const ta = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ta.current?.focus();
  }, []);

  const placeholder =
    '예) 지난주 계단에서 넘어져 병원에 다녀왔습니다. 보험금을 청구할 수 있는지 알고 싶어요.';

  const can = text.trim().length >= 5;

  return (
    <div className={s.shell} data-screen-label="03 상황 입력">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          {anonymous ? null : <PreStepper current="situation" />}
          <h1 className={s.title}>
            지금 어떤 <strong>상황</strong>이신가요?
          </h1>
          <p className={s.sub}>
            겪고 계신 상황을 평소 말씀하시는 그대로 적어주세요.<br />
            {anonymous
              ? '가입 정보 없이 일반 실손 표준약관 기준으로 먼저 안내해 드려요.'
              : '보험길잡이가 가입한 보험과 약관을 함께 살펴보고 안내해드립니다.'}
          </p>

          <div className={s.textareaWrap}>
            <textarea
              ref={ta}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={placeholder}
              maxLength={1000}
              aria-label="상황 입력"
            />
            <div className={s.bar}>
              <span className={s.count}>{text.length} / 1000자</span>
              <Button
                variant="primary"
                size="md"
                disabled={!can}
                onClick={() => can && onSubmit(text.trim())}
                withIcon
              >
                확인 시작하기
                <Icon name="arrow-right" size={16} />
              </Button>
            </div>
          </div>

          <p className={s.hint}>
            정확하지 않아도 괜찮습니다.<br />
            필요한 내용은 다음 단계에서 보험길잡이가 다시 질문드립니다.
          </p>
        </div>
      </main>
    </div>
  );
}
