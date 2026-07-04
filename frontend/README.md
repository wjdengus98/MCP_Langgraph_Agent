# 세이넌 챗봇 프론트엔드

React + Vite 기반 챗봇 UI. `chat_agent.py`(localhost:8001)의 SSE 스트리밍 응답을 실시간으로 렌더링합니다.

## 실행

```bash
# 1. MCP 서버 (포트 8000)
python mcp_server.py

# 2. 챗 에이전트 백엔드 (포트 8001)
python chat_agent.py

# 3. 프론트엔드 (포트 5173 고정 — 백엔드 CORS 허용 목록과 일치해야 함)
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:5173 접속.

## 구조

```
src/
├── App.jsx                  # 상태 관리, fetch + SSE 소비, 자동 스크롤
├── components/
│   ├── Composer.jsx         # 하단 입력창 (IME 조합 처리, 자동 높이, 중지 버튼)
│   ├── Message.jsx          # 말풍선, 도구 칩, 타이핑 인디케이터
│   ├── Welcome.jsx          # 첫 화면 + 추천 질문
│   └── Icons.jsx
├── lib/
│   ├── sse.js               # fetch ReadableStream → SSE 이벤트 파서
│   └── markdown.jsx         # [제목](URL)·**굵게**·`코드`·URL 자동 링크 렌더러
└── styles.css               # 딥 네이비 블루 테마
```

## 동작 방식

- `session_id`는 페이지 로드 시 `crypto.randomUUID()`로 생성해 세션 동안 유지. "새 대화" 버튼을 누르면 새 세션이 시작됩니다.
- `POST /chat` (multipart/form-data)의 응답 스트림을 직접 파싱합니다 — `EventSource`는 GET 전용이라 사용하지 않습니다.
- SSE 이벤트 처리: `text`(청크 이어붙이기) · `tool_start`(도구 칩 + 펄스 애니메이션) · `tool_end`(칩 완료 표시) · `error`(에러 박스).
