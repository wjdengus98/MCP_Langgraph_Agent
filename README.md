# MCP Agent Project

MCP(Model Context Protocol) 도구 서버 + LangGraph 에이전트 + React 프론트엔드로 구성된 개인용 AI 비서입니다. 날씨, 뉴스, KBO 순위, 웹 검색, 구글 캘린더 일정, 오늘의 명언 등을 대화로 물어볼 수 있습니다.

이 리포지토리는 **각자 자신의 API 키와 자신의 구글 계정으로 직접 배포해서 사용하는 구조**입니다. 즉, 아래 절차를 따라 fork/clone한 사람은 자기 자신의 OpenAI/Tavily 키, 자기 자신의 구글 캘린더로 동작하는 독립된 인스턴스를 갖게 됩니다.

## 1. 필요한 키 준비

### OpenAI API Key
https://platform.openai.com/api-keys 에서 발급.

### Tavily API Key
https://tavily.com 가입 후 대시보드에서 발급 (`tvly-...` 형태).

### Google Calendar OAuth 클라이언트 (credentials.json)
구글 캘린더 일정 조회 기능을 쓰려면 **본인 명의의 OAuth 클라이언트**를 직접 발급받아야 합니다.

1. [Google Cloud Console](https://console.cloud.google.com) 접속 → 새 프로젝트 생성
2. **APIs & Services → Library**에서 "Google Calendar API" 검색 후 활성화
3. **APIs & Services → OAuth consent screen** 설정 (User Type: External, 테스트 사용자로 본인 이메일 추가)
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
5. 생성된 클라이언트의 JSON 파일을 다운로드하여 프로젝트 루트에 `credentials.json`으로 저장 (이 파일은 `.gitignore`에 포함되어 있어 커밋되지 않습니다)

## 2. 로컬 설정

```bash
git clone <이 리포 URL>
cd mcp_agent_project
uv sync
```

프로젝트 루트에 `.env` 파일 생성:
```
OPENAI_API_KEY=본인의_openai_키
TAVILY_API_KEY=본인의_tavily_키
```

구글 캘린더 최초 인증 (브라우저가 열리며 본인 구글 계정으로 로그인):
```bash
python google_auth.py
```
성공하면 `token.json`이 생성됩니다.

## 3. 로컬 실행 확인

```bash
python mcp_server.py      # 터미널 1: MCP 도구 서버 (8000)
python chat_agent.py      # 터미널 2: 채팅 에이전트 서버 (8001)
cd frontend && npm install && npm run dev   # 터미널 3: 프론트엔드 (5173)
```

## 4. Railway 배포

1. GitHub에 본인 계정으로 fork/push
2. [Railway](https://railway.app) → **New Project → Deploy from GitHub repo** → 이 리포 선택
   - `railway.json`에 정의된 Dockerfile 빌드가 자동으로 사용됩니다
3. **Variables** 탭에서 아래 값 등록:

   | 변수명 | 값 |
   |---|---|
   | `OPENAI_API_KEY` | 본인의 OpenAI 키 |
   | `TAVILY_API_KEY` | 본인의 Tavily 키 |
   | `GOOGLE_TOKEN_JSON` | 로컬에서 생성한 `token.json` 파일의 내용 전체 (그대로 복사/붙여넣기) |

   `PORT`는 Railway가 자동으로 주입하므로 별도 설정 불필요.
4. 배포 완료 후 **Settings → Networking → Generate Domain**으로 퍼블릭 URL 생성

## 아키텍처 메모

- `mcp_server.py` (내부 8000 포트)와 `chat_agent.py` (외부 노출 포트)가 한 컨테이너 안에서 `start.sh`로 함께 실행됩니다.
- 구글 캘린더 인증은 `google_auth.py`에서 `GOOGLE_TOKEN_JSON` 환경 변수(배포용) → `token.json` 파일(로컬) → `credentials.json` + 브라우저 흐름(로컬 최초 인증) 순으로 시도합니다.
- `credentials.json`, `token.json`, `.env`는 모두 `.gitignore`/`.dockerignore`에서 제외되어 있어 리포지토리에 절대 커밋되지 않습니다. 반드시 본인 로컬에서 발급/생성한 후 Railway Variables로만 전달하세요.
