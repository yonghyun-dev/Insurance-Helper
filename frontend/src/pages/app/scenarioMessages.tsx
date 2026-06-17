import type { ReactNode } from 'react';
import InfoCard from '../../design-system/patterns/chat/InfoCard';
import ActionCard, { ActionCards } from '../../design-system/patterns/chat/ActionCard';
import DocRow, { DocChecklist } from '../../design-system/patterns/chat/DocRow';
import StateCard from '../../design-system/patterns/chat/StateCard';
import { Button } from '../../design-system';
import type { Role } from '../../design-system/patterns/chat/MessageBubble';

export type ChatScenario = 'main' | 'docs' | 'unclear' | 'low';

export interface ChatMessage {
  id: string;
  role: Role;
  name: string;
  initial?: string;
  time: string;
  body: ReactNode;
}

export interface ScenarioContext {
  scenario: ChatScenario;
  situation: string;
  userName: string;
  onSwitch: (scenario: ChatScenario | 'reset') => void;
  onOpenReview: () => void;
  onUpload: () => void;
  onAskMore: () => void;
}

const DEFAULT_SITUATION =
  '지난주 계단에서 넘어져 병원에 다녀왔습니다. 보험금을 청구할 수 있는지 알고 싶어요.';

export function buildScenarioMessages(ctx: ScenarioContext): ChatMessage[] {
  const { scenario, situation, userName, onSwitch, onOpenReview, onUpload, onAskMore } = ctx;

  const userInitial = userName?.[0] ?? '나';

  const userOpening: ChatMessage = {
    id: 'u-opening',
    role: 'user',
    name: userName,
    initial: userInitial,
    time: '오후 2:31',
    body: <p>{situation || DEFAULT_SITUATION}</p>,
  };

  if (scenario === 'main') {
    return [
      userOpening,
      {
        id: 'b-main-1',
        role: 'bot',
        name: '보험길잡이',
        time: '오후 2:31',
        body: (
          <>
            <p>
              가입하신 보험과 입력하신 상황을 바탕으로 확인을 시작했습니다.
              현재 내용만으로도 <strong>청구 가능성이 있는 보장 2건</strong>을 확인했어요.
            </p>
            <p>정확한 안내를 위해 몇 가지를 순서대로 확인하겠습니다.</p>
            <InfoCard
              title="현재 확인된 보장 후보"
              rows={[
                { label: '실손 의료비', value: '통원 치료비 본인부담 청구 가능성' },
                { label: '상해 보험', value: '일상생활 중 낙상 사고 보장 대상 가능성' },
                { label: '건강생활', value: '해당 진료는 위로금 특약 대상이 아닙니다' },
              ]}
            />
          </>
        ),
      },
      {
        id: 'b-main-2',
        role: 'bot',
        name: '보험길잡이',
        time: '오후 2:32',
        body: (
          <>
            <p>먼저 한 가지만 여쭤볼게요.</p>
            <p>
              병원 진료를 받으셨다면 <strong>통원 치료</strong>였는지{' '}
              <strong>입원 치료</strong>였는지만 알려주세요. 이 정보로 보장 범위가 달라집니다.
            </p>
            <ActionCards columns={2}>
              <ActionCard
                icon="information"
                title="통원 치료였어요"
                sub="당일 진료 후 귀가"
                onClick={() => onSwitch('docs')}
              />
              <ActionCard
                icon="information"
                title="입원 치료였어요"
                sub="1일 이상 입원"
                onClick={() => onSwitch('docs')}
              />
            </ActionCards>
          </>
        ),
      },
    ];
  }

  if (scenario === 'docs') {
    return [
      userOpening,
      {
        id: 'b-docs-1',
        role: 'bot',
        name: '보험길잡이',
        time: '오후 2:35',
        body: (
          <>
            <p>
              <strong>통원 치료</strong>로 확인했어요. 두 보험에서 청구 가능성이 있어
              아래 서류를 함께 안내해드립니다.
            </p>
            <p>
              현재 상황에서는 아래 서류가 필요할 수 있어요. 가지고 있는 서류부터 먼저 제출해 주세요.
            </p>
            <DocChecklist>
              <DocRow
                status="done"
                name="진료비 영수증"
                desc="마이데이터로 자동 확인됨 · 2026.05.18 · 강남구청병원"
              />
              <DocRow
                status="done"
                name="진료비 세부내역서"
                desc="병원 전송 정보로 자동 확인됨"
              />
              <DocRow
                status="required"
                name="통원확인서 또는 진단서"
                desc="진료받은 병원에서 발급 받아 업로드해 주세요"
                action="업로드"
                onAction={onUpload}
              />
              <DocRow
                status="required"
                name="신분증 사본"
                desc="주민등록증·운전면허증 중 한 가지"
                action="업로드"
                onAction={onUpload}
              />
              <DocRow
                status="optional"
                name="처방전"
                desc="약제비 청구가 필요한 경우에만 첨부합니다"
              />
            </DocChecklist>
            <p style={{ marginTop: 14 }}>
              서류는 한 번 올리시면 두 보험사에 함께 제출할 수 있도록 보험길잡이가 자동으로
              정리해드려요.
            </p>
          </>
        ),
      },
      {
        id: 'b-docs-2',
        role: 'bot',
        name: '보험길잡이',
        time: '오후 2:36',
        body: (
          <>
            <p>지금 통장 사본은 가지고 계신가요? 청구금 입금을 위해 한 번만 등록해두면 됩니다.</p>
            <ActionCards columns={2}>
              <ActionCard
                icon="arrow-up"
                title="지금 통장 사본 올리기"
                sub="JPG · PNG · PDF 가능"
                onClick={onUpload}
              />
              <ActionCard
                icon="document"
                title="청구 준비 내용 확인하기"
                sub="청구 직전 마지막 점검 화면"
                onClick={onOpenReview}
              />
            </ActionCards>
          </>
        ),
      },
    ];
  }

  if (scenario === 'unclear') {
    return [
      {
        id: 'u-unclear',
        role: 'user',
        name: userName,
        initial: userInitial,
        time: '오후 2:31',
        body: <p>저번에 좀 다쳤어요. 보험금 받을 수 있는지 알고 싶어요.</p>,
      },
      {
        id: 'b-unclear-1',
        role: 'bot',
        name: '보험길잡이',
        time: '오후 2:31',
        body: (
          <>
            <p>
              가입한 보험 3건은 확인했지만, 지금 알려주신 내용만으로는{' '}
              <strong>어떤 보장을 살펴봐야 할지 좁히기 어렵습니다.</strong>
            </p>
            <StateCard
              kind="warning"
              title="추가 정보가 필요합니다"
              actions={
                <Button variant="primary" size="md" onClick={onAskMore}>
                  여기서 더 자세히 입력
                </Button>
              }
            >
              사고나 치료 상황을 조금 더 자세히 알려주시면 관련 보장을 찾아 다시
              확인해드리겠습니다.
            </StateCard>
            <p style={{ marginTop: 12 }}>아래 항목 중 알고 계신 것만 알려주셔도 도움이 됩니다.</p>
            <ActionCards columns={2}>
              <ActionCard
                icon="information"
                title="병원에서 진료받았어요"
                sub="진료 종류·날짜"
                onClick={() => onSwitch('main')}
              />
              <ActionCard
                icon="warning-filled"
                title="사고가 있었어요"
                sub="언제 · 어디서 · 어떻게"
                onClick={() => onSwitch('main')}
              />
            </ActionCards>
          </>
        ),
      },
    ];
  }

  // low
  return [
    userOpening,
    {
      id: 'b-low-1',
      role: 'bot',
      name: '보험길잡이',
      time: '오후 2:31',
      body: (
        <>
          <p>가입하신 보험 3건과 약관을 살펴봤습니다.</p>
          <StateCard
            kind="info"
            title="현재 정보로는 청구 가능성이 낮아 보입니다"
            actions={
              <>
                <Button variant="primary" size="md" onClick={() => onSwitch('main')}>
                  특약 기준으로 다시 확인하기
                </Button>
                <Button variant="tertiary" size="md" onClick={() => onSwitch('reset')}>
                  상황 다시 입력하기
                </Button>
              </>
            }
          >
            말씀하신 상황은 가입하신 보장의 주요 항목 범위에 해당하지 않는 것으로 보입니다. 다만{' '}
            <strong>특약이나 세부 조건</strong>에 따라 결과가 달라질 수 있어요.
          </StateCard>
          <p style={{ marginTop: 12 }}>
            아래 항목 중 해당되시는 것이 있다면 알려주세요. 보장 범위가 달라질 수 있어요.
          </p>
          <ActionCards columns={2}>
            <ActionCard
              icon="information"
              title="입원 또는 수술을 받았어요"
              sub="입원·수술 특약 대상"
              onClick={() => onSwitch('main')}
            />
            <ActionCard
              icon="document"
              title="진단서를 받았어요"
              sub="질병 코드별 보장 가능성"
              onClick={() => onSwitch('main')}
            />
          </ActionCards>
        </>
      ),
    },
  ];
}

export const SCENARIO_HEAD: Record<ChatScenario, { title: string; sub: string }> = {
  main:    { title: '청구 가능 보장 확인', sub: '계단 낙상 · 통원치료 · 보험 3건 중 2건 청구 가능' },
  docs:    { title: '필요 서류 안내',       sub: '서류 5건 · 2건 자동 확인 · 1건 업로드 필요' },
  unclear: { title: '추가 정보 확인 중',    sub: '입력하신 내용으로는 보장 항목을 좁히기 어렵습니다' },
  low:     { title: '청구 가능성 재검토',   sub: '현재 정보로는 청구 가능성이 낮아 보입니다' },
};

export const SCENARIO_STATUS: Record<ChatScenario, { label: string; sub: string }> = {
  main:    { label: '청구 가능성 검토 중', sub: '약관과 비교해 보장 후보를 정리하고 있어요' },
  docs:    { label: '필요 서류 안내 중',   sub: '제출 서류를 안내하고 있어요' },
  unclear: { label: '추가 정보 확인 중',   sub: '몇 가지 더 여쭤볼게요' },
  low:     { label: '청구 가능성 낮음',    sub: '특약을 다시 확인할 수 있어요' },
};

export interface RailStep {
  id: string;
  label: string;
  sub?: string;
  status: 'done' | 'active' | 'waiting' | 'pending';
}

export const SCENARIO_RAIL: Record<ChatScenario, RailStep[]> = {
  main: [
    { id: 'r1', label: '가입 보험 확인',  sub: '3건 확인 완료',   status: 'done' },
    { id: 'r2', label: '관련 약관 확인',  sub: '실손·상해 약관',  status: 'done' },
    { id: 'r3', label: '청구 가능성 검토', sub: '진행 중',         status: 'active' },
    { id: 'r4', label: '필요 서류 안내',                            status: 'pending' },
    { id: 'r5', label: '청구서 작성 지원',                          status: 'pending' },
    { id: 'r6', label: '보험사 제출 안내',                          status: 'pending' },
  ],
  docs: [
    { id: 'r1', label: '가입 보험 확인',  sub: '3건 확인 완료',   status: 'done' },
    { id: 'r2', label: '관련 약관 확인',  sub: '실손·상해 약관',  status: 'done' },
    { id: 'r3', label: '청구 가능성 검토', sub: '2건 청구 가능',  status: 'done' },
    { id: 'r4', label: '필요 서류 안내',  sub: '제출 진행 중',    status: 'active' },
    { id: 'r5', label: '청구서 작성 지원',                          status: 'pending' },
    { id: 'r6', label: '보험사 제출 안내',                          status: 'pending' },
  ],
  unclear: [
    { id: 'r1', label: '가입 보험 확인',  sub: '3건 확인 완료',     status: 'done' },
    { id: 'r2', label: '관련 약관 확인',  sub: '검토 가능 항목 4개', status: 'done' },
    { id: 'r3', label: '추가 정보 확인',  sub: '답변 대기 중',       status: 'waiting' },
    { id: 'r4', label: '청구 가능성 검토',                            status: 'pending' },
    { id: 'r5', label: '필요 서류 안내',                              status: 'pending' },
  ],
  low: [
    { id: 'r1', label: '가입 보험 확인',  sub: '3건 확인 완료',     status: 'done' },
    { id: 'r2', label: '관련 약관 확인',                              status: 'done' },
    { id: 'r3', label: '청구 가능성 검토', sub: '낮음으로 판단',    status: 'done' },
    { id: 'r4', label: '추가 확인 필요',   sub: '특약 재검토 가능',  status: 'waiting' },
    { id: 'r5', label: '필요 서류 안내',                              status: 'pending' },
  ],
};
