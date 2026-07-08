// 답변 텍스트의 마크다운 렌더링(볼드·목록 등). 인용 약관 표는 CitationList 가 별도로
// 정리하므로 여기서는 GFM(표·취소선·자동링크)을 쓰지 않는다 — 의료코드 'F04~F99' 등의
// '~' 가 취소선으로 오인되는 부작용을 방지.
import ReactMarkdown from 'react-markdown';
import s from './Markdown.module.css';

export default function Markdown({ children }: { children: string }) {
  return (
    <div className={s.md}>
      <ReactMarkdown
        components={{
          a: ({ node: _node, ...props }) => (
            <a target="_blank" rel="noopener noreferrer" {...props} />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
