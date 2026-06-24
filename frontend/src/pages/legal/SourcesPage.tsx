// 데이터 출처 — 본 서비스가 인용하는 공개 자료 카드. 외부 링크는 분기 1회 점검.
import { Fragment } from 'react';
import DocShell, { Note } from './DocShell';
import s from './legal.module.css';

type SourceKind = 'terms' | 'law' | 'standard' | 'disease' | 'calc';

interface Source {
  kind: SourceKind;
  tag: string;
  title: string;
  operator: string;
  description: string;
  meta: { label: string; value: string }[];
  externalLink?: { href: string; label: string };
}

const CARD_CLASS: Record<SourceKind, string> = {
  terms: s.srcCardTerms,
  law: s.srcCardLaw,
  standard: s.srcCardStandard,
  disease: s.srcCardDisease,
  calc: s.srcCardCalc,
};

const TAG_LABEL: Record<SourceKind, string> = {
  terms: '약관 — 보험사 공식 PDF',
  law: '법령 — 정부 공공저작물',
  standard: '표준 — 협회 공식 자료',
  disease: '진단코드 — 공공데이터',
  calc: '계산 — 본 서비스 내장 로직',
};

const SOURCES: Source[] = [
  {
    kind: 'terms',
    tag: '약관',
    title: '보험사 공식 약관 PDF',
    operator: '각 손해보험사 (삼성화재·현대해상·메리츠화재·한화손해보험·롯데손해보험)',
    description:
      '인용은 보험사 공식 약관의 조항 번호·페이지·원문 발췌 형태로 노출되며, 약관 PDF 자체는 저작권상 본 서비스에서 직접 제공하지 않습니다. 원문 확인은 각 보험사 공식 홈페이지에서 가능합니다.',
    meta: [
      { label: '현재 적재', value: '실손의료보험 5개사 (삼성화재·현대해상·메리츠화재·한화손해보험·롯데손해보험)' },
      { label: '갱신 주기', value: '분기' },
      { label: '인용 방식', value: '조항 번호 + 페이지 + 원문 발췌 (저작권 인용 범위 내)' },
    ],
  },
  {
    kind: 'law',
    tag: '법령',
    title: '국가법령정보센터',
    operator: '법제처',
    description:
      '보험업법·상법(보험편)·국민건강보험법 등 실손 청구 관련 법령을 인용합니다. 법령 본문은 공공저작물로 자유 이용이 가능합니다.',
    meta: [
      { label: '활용 법령', value: '보험업법, 상법(보험편), 국민건강보험법, 약관규제법' },
      { label: 'API', value: 'open.law.go.kr' },
      { label: '갱신 주기', value: '30일 캐시' },
    ],
    externalLink: { href: 'https://open.law.go.kr/', label: '국가법령정보센터 OPEN API' },
  },
  {
    kind: 'standard',
    tag: '표준',
    title: '실손의료보험 표준약관',
    operator: '금융감독원',
    description:
      '실손의료보험은 금융감독원이 정한 표준약관을 기반으로 합니다. 본 서비스는 각 보험사가 이 표준약관을 반영해 공시한 약관을 적재하며, 보장·면책·자기부담금 판단의 기준으로 삼습니다.',
    meta: [
      { label: '법적 근거', value: '보험업감독업무 시행세칙 별표 15 (실손의료보험 표준약관)' },
      { label: '갱신 주기', value: '표준약관 개정 시' },
    ],
  },
  {
    kind: 'disease',
    tag: '진단코드',
    title: '한국표준질병분류 (KCD-8)',
    operator: '건강보험심사평가원 (HIRA)',
    description:
      '사고질병 영역에서 진단명을 표준 코드로 변환할 때 사용합니다(예: "발목 골절" → S82.x). 사용자의 입력 평문은 외부로 전달되지 않으며, 시스템이 추출한 진단명만 조회됩니다.',
    meta: [
      { label: '활용 시점', value: '사고질병 영역 — 진단명 → 코드 변환' },
      { label: 'API', value: 'data.go.kr (공공데이터포털)' },
      { label: '갱신 주기', value: '7일 캐시' },
    ],
    externalLink: { href: 'https://www.data.go.kr/', label: '공공데이터포털 (data.go.kr)' },
  },
  {
    kind: 'calc',
    tag: '계산',
    title: '본 서비스 내장 계산',
    operator: 'Deterministic Python 모듈',
    description:
      '보험금 산정에 사용되는 산수(손해액 × 지급률 등)는 본 서비스의 결정적(deterministic) 코드로 수행됩니다. AI 모델의 환각을 회피하기 위해 LLM 은 산수 계산에 직접 사용되지 않습니다.',
    meta: [
      { label: '용도', value: '보험금 산정, 자기부담금 공제, 한도 비교' },
      { label: '출처', value: '산정 공식은 각 약관·법령에 명시된 식 사용' },
      { label: '검증', value: '단위 테스트 + 회귀 케이스 보관' },
    ],
  },
];

export default function SourcesPage() {
  return (
    <DocShell
      title="데이터 출처"
      lede="본 서비스의 모든 답변은 검증된 공개 자료를 인용합니다. 카드 좌측의 색 라인이 출처 종류를 나타냅니다."
      updatedAt="2026-06-24"
      badge="투명성 · 공공 데이터 기반"
      related={[
        { to: '/legal/disclaimer', label: '면책 및 이용약관' },
        { to: '/legal/privacy', label: '개인정보 처리방침' },
        { to: '/legal/accessibility', label: '접근성 안내' },
      ]}
    >
      <div className={s.srcList}>
        {SOURCES.map((src) => (
          <article
            key={src.kind}
            className={`${s.srcCard} ${CARD_CLASS[src.kind]}`}
            aria-label={TAG_LABEL[src.kind]}
          >
            <div className={s.srcTag} aria-hidden="true">▌ {src.tag}</div>
            <div className={s.srcTitle}>{src.title}</div>
            <div className={s.srcOperator}>운영: {src.operator}</div>
            <p className={s.srcDesc}>{src.description}</p>
            <div className={s.srcMeta}>
              {src.meta.map((m) => (
                <Fragment key={m.label}>
                  <div className={s.srcMetaLabel}>{m.label}</div>
                  <div className={s.srcMetaValue}>{m.value}</div>
                </Fragment>
              ))}
            </div>
            {src.externalLink && (
              <a
                className={s.srcLink}
                href={src.externalLink.href}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`새 탭에서 ${src.externalLink.label} 열기`}
              >
                {src.externalLink.label}
                <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
                  <path fill="currentColor" d="M9 1v1h4.3L6 9.3l.7.7L14 2.7V7h1V1zM2 3v11h11V8h-1v5H3V4h5V3z" />
                </svg>
              </a>
            )}
          </article>
        ))}
      </div>

      <Note title="외부 링크 점검">
        외부 링크는 분기 1회 점검을 거치며, 깨진 링크 발견 시 즉시 갱신합니다.
        본 페이지에 노출된 외부 사이트의 콘텐츠는 본 서비스 제공자의 통제 범위 밖이며,
        해당 운영 기관의 약관과 정책을 따릅니다.
      </Note>
    </DocShell>
  );
}
