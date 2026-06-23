# ERD — 전체 테이블 관계도

Sprint 1 SQLite 메타데이터 스키마를 시각화한다. Chroma 컬렉션은 별도(임베딩 + 검색 메타) 이지만 `chunk.id` 를 키로 SQLite `clause_chunks` 와 연결된다.

```mermaid
erDiagram
    INSURER ||--o{ PRODUCT : "판매한다"
    PRODUCT ||--o{ PRODUCT_VERSION : "버전을 가진다"
    PRODUCT_VERSION ||--o{ DOCUMENT : "문서를 가진다"
    DOCUMENT ||--o{ CLAUSE_CHUNK : "청크로 분할된다"
    CLAUSE_CHUNK ||--o| CLAUSE_CHUNK : "부모 조항을 참조"

    INSURER {
        TEXT id PK
        TEXT name
        TEXT homepage_url
        TIMESTAMP created_at
    }
    PRODUCT {
        TEXT id PK
        TEXT insurer_id FK
        TEXT area
        TEXT name
        TIMESTAMP created_at
    }
    PRODUCT_VERSION {
        INTEGER id PK
        TEXT product_id FK
        DATE valid_from
        DATE valid_to
        TEXT version_label
        BOOLEAN is_active
        TIMESTAMP created_at
    }
    DOCUMENT {
        INTEGER id PK
        INTEGER version_id FK
        TEXT doc_type
        TEXT file_path
        TEXT file_sha256
        INTEGER page_count
        TEXT parser_version
        TIMESTAMP extracted_at
    }
    CLAUSE_CHUNK {
        TEXT id PK
        INTEGER document_id FK
        TEXT parent_chunk_id FK
        TEXT chunk_type
        TEXT clause_no
        TEXT sub_no
        INTEGER page_start
        INTEGER page_end
        INTEGER token_count
        TEXT text
        TEXT summary
        TEXT tags_json
        TIMESTAMP created_at
    }
```

요약: 보험사 → 상품 → 판매기간 버전 → PDF 문서 → 의미 단위 청크의 계층. 청크는 부모 조항을 self-ref 한다.
