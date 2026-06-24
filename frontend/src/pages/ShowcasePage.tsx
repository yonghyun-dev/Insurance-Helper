import { useState } from 'react';
import {
  Accordion,
  Avatar,
  Button,
  Checkbox,
  Field,
  Icon,
  Modal,
  Notification,
  Radio,
  Select,
  Tabs,
  Tag,
  Tile,
  Toggle,
} from '../design-system';
import s from './ShowcasePage.module.css';

const SWATCHES: Array<{ name: string; varName: string; hex: string }> = [
  { name: 'Blue 10',  varName: '--blue-10',  hex: '#edf5ff' },
  { name: 'Blue 20',  varName: '--blue-20',  hex: '#d0e2ff' },
  { name: 'Blue 60',  varName: '--blue-60',  hex: '#0f62fe' },
  { name: 'Blue 70',  varName: '--blue-70',  hex: '#0043ce' },
  { name: 'Blue 80',  varName: '--blue-80',  hex: '#002d9c' },
  { name: 'Blue 100', varName: '--blue-100', hex: '#001141' },
  { name: 'Gray 10',  varName: '--gray-10',  hex: '#f4f4f4' },
  { name: 'Gray 20',  varName: '--gray-20',  hex: '#e0e0e0' },
  { name: 'Gray 50',  varName: '--gray-50',  hex: '#8d8d8d' },
  { name: 'Gray 70',  varName: '--gray-70',  hex: '#525252' },
  { name: 'Gray 80',  varName: '--gray-80',  hex: '#393939' },
  { name: 'Gray 100', varName: '--gray-100', hex: '#161616' },
];

const TYPE_ROWS: Array<{ utility: string; sample: string }> = [
  { utility: 'ty-heading-07', sample: '디스플레이 Light 54px' },
  { utility: 'ty-heading-06', sample: '디스플레이 Light 42px' },
  { utility: 'ty-heading-05', sample: '제목 Regular 32px' },
  { utility: 'ty-heading-04', sample: '제목 Regular 28px' },
  { utility: 'ty-heading-03', sample: '제목 Regular 20px' },
  { utility: 'ty-heading-02', sample: '제목 SemiBold 16px' },
  { utility: 'ty-heading-01', sample: '제목 SemiBold 14px' },
  { utility: 'ty-body-02',    sample: '본문 Regular 16px — 보험길잡이 안내 문구' },
  { utility: 'ty-body-01',    sample: '본문 Regular 14px — 짧은 본문' },
  { utility: 'ty-label-02',   sample: '라벨 14px' },
  { utility: 'ty-label-01',   sample: '라벨 12px' },
  { utility: 'ty-helper-01',  sample: '도움말 12px' },
  { utility: 'ty-code-02',    sample: 'IBM Plex Mono 14px' },
];

export default function ShowcasePage() {
  const [tab, setTab] = useState('실손');
  const [select, setSelect] = useState('losang');
  const [check1, setCheck1] = useState(true);
  const [check2, setCheck2] = useState(false);
  const [radio, setRadio] = useState('self');
  const [tog1, setTog1] = useState(true);
  const [tog2, setTog2] = useState(false);
  const [modal, setModal] = useState(false);

  return (
    <div className={s.page}>
      <header className={s.intro}>
        <h1 className={s.introHead}>보험길잡이 Design System</h1>
        <p className={s.introSub}>
          IBM Carbon Design System v11 White theme 기반 · 한국어 공공 서비스 톤 · React + TypeScript 포팅.
          모든 토큰과 클래스명은 원본 디자인 시스템과 1:1 매칭됩니다.
        </p>
      </header>

      {/* Color */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Color</h2>
        <p className="ty-helper-01">브랜드 · 그레이 스케일 (Carbon White theme)</p>
        <div className={s.colorGrid}>
          {SWATCHES.map((sw) => (
            <div key={sw.varName} className={s.swatch}>
              <div className={s.swatchChip} style={{ background: sw.hex }} />
              <div className={s.swatchLabel}>{sw.name}</div>
              <div className={s.swatchHex}>{sw.hex}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Typography */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Typography</h2>
        <p className="ty-helper-01">IBM Plex Sans KR · Productive type scale</p>
        <div>
          {TYPE_ROWS.map((row) => (
            <div key={row.utility} className={s.typeRow}>
              <div className={s.typeMeta}>{row.utility}</div>
              <div className={row.utility}>{row.sample}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Button */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Button</h2>

        <div className={s.lbl}>Variants</div>
        <div className={s.demo}>
          <Button variant="primary" withIcon>
            Primary <Icon name="arrow-right" size={16} />
          </Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="tertiary">Tertiary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="primary" disabled>Disabled</Button>
        </div>

        <div className={s.lbl}>Sizes</div>
        <div className={s.demo}>
          <Button size="sm">SM 32</Button>
          <Button size="md">MD 40</Button>
          <Button>LG 48 (default)</Button>
          <Button size="xl">XL 64</Button>
          <Button size="2xl">2XL 80</Button>
        </div>

        <div className={s.lbl}>Icon-only</div>
        <div className={s.demo}>
          <Button iconOnly variant="ghost"><Icon name="settings" size={16} /></Button>
          <Button iconOnly variant="ghost" size="md"><Icon name="copy" size={16} /></Button>
          <Button iconOnly variant="ghost" size="sm"><Icon name="close" size={16} /></Button>
          <Button iconOnly variant="secondary"><Icon name="add" size={16} /></Button>
        </div>
      </section>

      {/* Form Fields */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Form Fields</h2>
        <div className={s.grid2}>
          <Field label="이름" defaultValue="김민서" helper="실명을 입력해 주세요." />
          <Field
            label="생년월일"
            defaultValue="2025-15-99"
            error="유효한 날짜 형식이 아닙니다. (예: 1980-01-15)"
          />
          <Field label="전화번호 (비활성)" placeholder="010-0000-0000" disabled />
          <Field label="검색" placeholder="보험 종류, 약관 검색" leadingIcon="search" />
        </div>
      </section>

      {/* Selection Controls */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Selection Controls</h2>

        <div className={s.grid2}>
          <div className={s.col}>
            <div className={s.lbl}>Checkbox</div>
            <Checkbox checked={check1} onChange={(e) => setCheck1(e.target.checked)}>
              실손 의료비 보험
            </Checkbox>
            <Checkbox checked={check2} onChange={(e) => setCheck2(e.target.checked)}>
              비급여 특약
            </Checkbox>
            <Checkbox checked disabled>3대비급여 특약 (비활성)</Checkbox>
          </div>

          <div className={s.col}>
            <div className={s.lbl}>Radio</div>
            <Radio name="r1" checked={radio === 'self'} onChange={() => setRadio('self')}>본인</Radio>
            <Radio name="r1" checked={radio === 'spouse'} onChange={() => setRadio('spouse')}>배우자</Radio>
            <Radio name="r1" disabled>부모 (비활성)</Radio>
          </div>

          <div className={s.col}>
            <div className={s.lbl}>Toggle</div>
            <Toggle
              checked={tog1}
              onChange={(e) => setTog1(e.currentTarget.checked)}
              label="알림 받기"
              stateLabel={tog1 ? '켜짐' : '꺼짐'}
            />
            <Toggle
              checked={tog2}
              onChange={(e) => setTog2(e.currentTarget.checked)}
              label="이메일 수신"
              stateLabel={tog2 ? '켜짐' : '꺼짐'}
            />
          </div>

          <div className={s.col}>
            <div className={s.lbl}>Tag</div>
            <div className={s.demo}>
              <Tag>실손</Tag>
              <Tag color="blue">통원</Tag>
              <Tag color="green">완료</Tag>
              <Tag color="red">긴급</Tag>
              <Tag filter onDismiss={() => alert('필터 해제')}>필터 적용</Tag>
            </div>
          </div>
        </div>
      </section>

      {/* Select */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Select</h2>
        <Select
          value={select}
          onChange={setSelect}
          options={[
            { value: 'losang', label: '실손 의료비 보험' },
            { value: 'nonpay', label: '비급여 특약' },
            { value: 'cancer', label: '암 보험' },
            { value: 'travel', label: '여행자 보험' },
          ]}
        />
      </section>

      {/* Notifications */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Notifications</h2>
        <div className={s.notifList}>
          <Notification
            kind="info"
            title="새 약관이 적용되었습니다"
            onClose={() => undefined}
          >
            2026년 6월 1일부터 변경된 약관이 적용됩니다.
          </Notification>
          <Notification kind="success" title="상담 내용이 저장되었습니다">
            마이페이지에서 다시 열람할 수 있습니다.
          </Notification>
          <Notification kind="warning" title="개인정보가 포함된 답변입니다">
            화면 캡처에 주의해 주세요.
          </Notification>
          <Notification kind="error" title="답변을 가져오지 못했습니다">
            네트워크 연결을 확인하고 다시 시도해 주세요.
          </Notification>
        </div>
      </section>

      {/* Tiles · Tabs · Accordion */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Tiles · Tabs · Accordion</h2>

        <div className={s.lbl}>Tiles</div>
        <div className={s.grid2}>
          <Tile>
            <strong>실손 의료비</strong>
            <p className="ty-helper-01" style={{ marginTop: 8 }}>표준 약관 · 갱신형</p>
          </Tile>
          <Tile clickable>
            <strong>실손 약관 비교</strong>
            <p className="ty-helper-01" style={{ marginTop: 8 }}>5개 보험사 약관 대조</p>
          </Tile>
          <Tile accent>
            <strong>암 진단비 추천</strong>
            <p className="ty-helper-01" style={{ marginTop: 8 }}>맞춤형 — 김민서 고객님</p>
          </Tile>
          <Tile selected>
            <strong>여행자 보험 (선택됨)</strong>
            <p className="ty-helper-01" style={{ marginTop: 8 }}>해외 여행 14일 기준</p>
          </Tile>
        </div>

        <div className={s.lbl} style={{ marginTop: 32 }}>Tabs</div>
        <Tabs
          activeId={tab}
          onChange={setTab}
          items={[
            { id: '실손', label: '실손 의료비' },
            { id: '비급여', label: '비급여' },
            { id: '암', label: '암 보험' },
            { id: '기타', label: '기타' },
          ]}
        />

        <div className={s.lbl} style={{ marginTop: 32 }}>Accordion</div>
        <Accordion
          items={[
            {
              id: 'a1',
              title: '실손 의료비 보험이란?',
              defaultOpen: true,
              content: (
                <p>실손 의료비 보험은 병원 진료비 중 본인이 부담한 금액을 보장하는 보험입니다.</p>
              ),
            },
            {
              id: 'a2',
              title: '가입 시 유의사항',
              content: <p>고지 의무를 성실히 이행해야 보장 거절을 예방할 수 있습니다.</p>,
            },
            {
              id: 'a3',
              title: '청구 절차',
              content: <p>진료 후 30일 이내 청구를 권장합니다. 진료비 영수증과 진단서가 필요합니다.</p>,
            },
          ]}
        />
      </section>

      {/* Avatar */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Avatar</h2>
        <div className={s.demo}>
          <Avatar kind="bot">B</Avatar>
          <Avatar kind="user">민서</Avatar>
          <Avatar kind="bot" size="lg">B</Avatar>
          <Avatar kind="user" size="lg">민</Avatar>
        </div>
      </section>

      {/* Modal */}
      <section className={s.section}>
        <h2 className={s.sectionTitle}>Modal</h2>
        <div className={s.demo}>
          <Button onClick={() => setModal(true)}>모달 열기</Button>
        </div>
        <Modal
          open={modal}
          onClose={() => setModal(false)}
          kind="info"
          eyebrow="안내"
          title="상담을 시작할까요?"
          footer={
            <>
              <Button variant="secondary" onClick={() => setModal(false)}>취소</Button>
              <Button variant="primary" onClick={() => setModal(false)}>시작하기</Button>
            </>
          }
        >
          상담은 약 3분이 소요됩니다. 답변은 참고용이며, 정확한 가입·청구는 보험사에 문의해 주세요.
        </Modal>
      </section>
    </div>
  );
}
