"""
Chat Agent Server - MCP 도구를 사용하는 LangGraph 에이전트 서버

[전체 동작 흐름]
1. MCP 서버(mcp_server.py)에 연결하여 7개 도구를 로드
2. LangGraph ReAct 에이전트 생성 (도구를 자동으로 선택하고 실행)
3. FastAPI 서버로 사용자 메시지를 받음
4. 에이전트가 필요한 도구를 선택해서 실행
5. 결과를 SSE(Server-Sent Events)로 스트리밍 응답
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
#from langchain.agents import create_agent
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import uvicorn
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

def create_prompt_template() -> ChatPromptTemplate:
    """
    에이전트를 위한 프롬프트 템플릿을 생성합니다.
    
    [역할]
    - 에이전트의 정체성과 행동 원칙을 정의
    - 어떤 도구들을 사용할 수 있는지 설명
    - 사용자와 소통하는 방식 지정
    
    Returns:
        ChatPromptTemplate: LangChain 프롬프트 템플릿
    """
    system_prompt = """당신은 친절하고 도움이 되는 AI 어시스턴트 "세이넌"입니다. 

    다음과 같은 도구들을 활용하여 사용자를 도와드릴 수 있습니다:
    - 웹페이지의 텍스트 콘텐츠를 스크랩하여 정보를 가져올 수 있습니다
    - 도시 이름을 받아 해당 도시의 현재 날씨 정보를 제공할 수 있습니다
    - 구글 RSS 피드에서 최신 뉴스와 URL을 가져올 수 있습니다
    - 한국 프로야구 구단의 랭킹 정보를 제공할 수 있습니다
    - 일정과 스케줄 정보를 확인할 수 있습니다
    - 사용자에게 영감을 주는 명언과 응원 메시지를 제공할 수 있습니다
    - 사용자의 하루 일정 준비를 도와주는 브리핑 기능이 있습니다. 
    사용자가 위치한 곳을 안다면 바로 brief_today() 도구의 지침을 따르면 됩니다. 아니라면, 위치를 물어보고나서 도구의 지침을 따릅니다. 

    사용자와의 대화에서 다음 원칙을 지켜주세요:
    1. 항상 친절하고 정중한 태도로 응답해주세요
    2. 사용자의 질문을 정확히 이해하고 관련된 도구를 적절히 활용해주세요
    3. 최신 뉴스를 요청받으면, 도구의 출력을 그대로 출력하면 됩니다.
    4. 응답은 명확하고 이해하기 쉽게 구성해주세요
    5. 필요시 추가 정보나 설명을 제공하여 사용자에게 더 나은 도움을 주세요
    6. 링크가 포함된 정보를 제공할 때는 [제목](URL) 형태의 마크다운 링크로 제공해주세요
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),  # 대화 기록이 들어갈 자리
        ]
    )

def create_agent(tools):
    """주어진 도구를 사용하여 에이전트를 생성"""
    memory = InMemorySaver()
    prompt = create_prompt_template()
    llm = ChatOpenAI(model="gpt-4o-mini")
    return create_react_agent(llm,tools, checkpointer=memory, prompt = prompt)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fast API 애플리케이션의 생명주기 동안 MCP 연결 및 에이전트 설정 관리"""
    print("애플리케이션 시작: MCP 서버에 연결하고 에이전트를 설정합니다.")
    
    async with streamable_http_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            # 세션 초기화
            await session.initialize()
            
            # MCP 서버의 모든 도구를 Langchain 형식으로 로드
            tools = await load_mcp_tools(session)
            
            print(f"mcp 도구로드 완료: 총 {len(tools)}개")
            for tool in tools:
                print(f" - {tool.name}")
                
            # 로드한 도구들로 에이전트 생성
            app.state.agent_executor = create_agent(tools)
            print("에이전트 설정 완료. 애플리케이션이 준비되었습니다.")
            yield
            
    print("애플리케이션 종료.")
    app.state.agent_executor = None

# lifespan 관리자를 사용하여 FastAPI 앱 인스턴스 생성
app = FastAPI(lifespan=lifespan)

# CORS 설정 
# React 앱(localhost:5173)에서 이 API(localhost:8001)를 호출할 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 개발 서버 주소
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

#==================================
# API 엔드포인트
#==================================

@app.get("/")
async def root():
    return {"status": "ok", "message": "I'm ready!"}

@app.get("/health")
async def health_check():
    agent_ready = hasattr(app.state, 'agent_executor')
    #             app.state 확인만
    
    return {"status": "healthy", "agent_ready": agent_ready}
       

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)