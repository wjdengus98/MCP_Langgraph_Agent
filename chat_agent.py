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
from langchain.agents import create_react_agent
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
    system_prompt = """당신은 친절하고 도움이 되는 AI 어시스턴트 "금토깽"입니다. 

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
    

if __name__ == "__main__":
    pass