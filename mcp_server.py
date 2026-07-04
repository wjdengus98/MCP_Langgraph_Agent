"""
MCP Server - AI Agent를 위한 도구 모음

제공하는 도구:
1. scrape_page_text: 웹페이지 텍스트 스크래핑
2. get_weather: 도시별 날씨 조회
3. get_news_headlines: 구글 RSS 뉴스 헤드라인
4. get_kbo_rank: KBO 프로야구 순위 (KBO 공식 사이트, 시즌 자동 반영)
5. today_schedule: 오늘의 일정 (Mock 데이터) -> 노션, 구글 스케줄러 연동
6. daily_quote: 영감을 주는 명언 생성
7. web_search_tavily: langchain-tavily(TavilySearch) 기반 실시간 웹 검색
8. brife_today: 종합 브리핑 오케스트레이터
"""

import json
import logging
import feedparser
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from mcp.server.fastmcp import FastMCP
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from dotenv import load_dotenv
import os
from googleapiclient.discovery import build
from datetime import datetime
import pytz

# 환경 설정
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 서버 인스턴스 생성
mcp = FastMCP("MCP-Agent-Server")

# Tavily 웹 검색 (WebResearchAgent 가 Tavily 원격 MCP 서버에 접속해서 사용)
# TAVILY_API_KEY 가 .env 에 없으면 도구 호출 시점에 안내 메시지 반환
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# 웹페이지 스크래핑 도구
@mcp.tool()
def scrape_page_text(url:str) -> str:
    """웹페이지의 텍스트 콘텐츠 스크랩
    
        Args:
            url: 스크랩할 웹페이지 URL
        Returns:
            추출된 텍스트 or 에러메시지
    """
    try:
        logger.info(f"웹페이지 스크래핑: {url}")
            
        #User agent 헤더 추가 (사이트 차단 방지)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # script, style, nav, footer, header 로 감싸져있는 tag 제거
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        if soup.body:
            text = soup.body.get_text(separator=" ", strip=True)
            cleaned_text = " ".join(text.split())
            
            logger.info(f"스크래핑 완료 {len(cleaned_text)} 자 추출")
            return cleaned_text[:5000]
        
        return "본문 내용을 찾을 수 없습니다."
    
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP 에러 발생: {e.response.status_code}"
        logger.error(error_msg)
        return error_msg
    except httpx.TimeoutException:
        error_msg = "요청 시간 초과: 웹페이지 응답이 너무 느립니다."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"스크래핑 실패: {str(e)}"
        logger.error(error_msg)
        return error_msg

# 도시명을 좌표로 변환하는 헬퍼 함수
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def get_coordinates(city_name: str) -> tuple[float, float]:
    """도시 이름을 받아 위도/경도를 반환 하는 함수"""
    try:
        geolocator = Nominatim(user_agent="weather_app_langgraph")
        location = geolocator.geocode(city_name)
        
        if location:
            logger.info(f"좌표 찾음: {city_name} -> ({location.latitude}, {location.longitude})")
            return location.latitude, location.longitude
        raise ValueError(f"'{city_name}'의 좌표를 찾을 수 없습니다. 도시 이름을 확인해주세요.")
    
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning(f"Geocoder 에러: {e}, 재시도 중...")
        raise  # Retry 데코레이터가 처리

@mcp.tool()
def get_weather(city_name:str) -> str:
    """도시 이름을 받아 현재 날씨 정보 반환"""

    logger.info(f"날씨 조회 시작: {city_name}")
    
    # 위도/경도 조회
    latitude, longitude = get_coordinates(city_name)

    # OPEN METRO API
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true&timezone=Asia%2FSeoul"
    
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    
    result = response.json()
    
    # 사람이 읽기 쉽게 포맷팅
    current = result.get('current_weather', {})
    weather_info = {
        "도시": city_name,
        "온도": f"{current.get('temperature', 'N/A')}°C",
        "풍속": f"{current.get('windspeed', 'N/A')} km/h",
        "날씨코드": current.get('weathercode', 'N/A'),
        "시간": current.get('time', 'N/A')
    }
    
    logger.info(f"날씨 조회 완료: {city_name} - {weather_info['온도']}")
    return json.dumps(weather_info, ensure_ascii=False, indent=2)


#3. 구글 뉴스 헤드라인
@mcp.tool()
def get_news_headlines(max_items: int = 10) -> str:
    """구글 RSS 피드에서 최신 뉴스와 URL 반환""" 
    try:
        logger.info(f"뉴스 조회 시작 최대 {max_items}개")
        
        rss_url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            return "뉴스를 가져올 수 없습니다."
        
        news_list =[]
        for i, entry in enumerate(feed.entries[:max_items], 1):
            title = getattr(entry, "title", "제목 없음")
            link = getattr(entry, "link", "#")
            
            # None 값 처리
            if not title or title == None:
                title = "제목 없음"
            if not link or link == None:
                link = "#"
            
            # 마크다운 형식 포맷팅
            news_item = f"{i}. [{title}]({link})"
            news_list.append(news_item)
            
        logger.info(f"뉴스 조회 완료: {len(news_list)}개 항목")
        
        # 번호가 매겨진 리스트를 문자열로 반환
        return "\n".join(news_list)
    
    except Exception as e:
        error_msg = f"뉴스 조회 실패: {str(e)}"
        logger.error(error_msg)
        return error_msg

#4. KBO 프로야구 순위 가져오기 (KBO 고ㅓㅇ식 사이트 - 시즌 자동 반영, 하드코딩 불필요)
@mcp.tool()
def get_kbo_rank() -> str:
    """
    한국 프로야구(KBO) 구단의 현재 시즌 순위를 KBO 공식 홈페이지에서 가져옵니다.
    이 페이지는 시즌을 별도로 지정하지 않아도 항상 '현재 진행 중인 시즌'의
    최신 순위를 보여주므로, 매 시즌 코드를 갱신할 필요가 없습니다.
 
    주의: 이 도구는 오늘 기준 '현재 진행 중인 시즌'의 순위만 제공합니다.
    2025년 등 이미 종료된 과거 시즌의 순위를 물어보는 경우에는 이 도구 대신
    web_search_tavily(query="2025 KBO 순위") 처럼 웹 검색 도구를 사용하세요.
 
    Returns:
        KBO 순위 정보 문자열
    """
    try:
        logger.info("KBO 순위 조회 시작 (KBO 공식 사이트)")
        
        url = "https://www.koreabaseball.com/Record/TeamRank/TeamRankDaily.aspx"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = httpx.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        
        # 페이지 내 <table> 을 DataFrame 으로 파싱 (순위표가 첫 번째 테이블)
        tables = pd.read_html(resp.text)
        if not tables:
            return "KBO 순위 데이터를 가져올 수 없습니다."
        
        rank_df = tables[0]
        
        result = []
        result.append("## 📊 KBO 리그 순위 (실시간, KBO 공식 사이트 기준)\n")
        
        for _, row in rank_df.iterrows():
            try:
                rank_line = (
                    f"{row['순위']}위: {row['팀명']} - "
                    f"{row['승']}승 {row['패']}패 {row['무']}무 "
                    f"(승률 {row['승률']}, 게임차 {row['게임차']}, "
                    f"최근10경기 {row['최근10경기']}, 연속 {row['연속']})"
                )
                result.append(rank_line)
            except KeyError:
                # 사이트 테이블 컬럼명이 바뀐 경우를 대비한 폴백
                result.append(" | ".join(str(v) for v in row.values))
        
        logger.info("KBO 순위 조회 완료")
        return "\n".join(result)
        
    except Exception as e:
        error_msg = f"KBO 순위 조회 실패: {str(e)}"
        logger.error(error_msg)
        return error_msg


# Google calender
@mcp.tool()
def today_schedule() -> str:
    """Google Calendar에서 오늘의 일정을 가져옵니다."""

    logger.info("Google Calendar 일정 조회 시작")

    # 인증 (배포 환경에서 인증 정보가 없으면 도구가 죽지 않고 안내 메시지를 반환)
    from google_auth import get_credentials
    try:
        creds = get_credentials()
    except Exception as e:
        logger.warning(f"Google Calendar 인증 실패: {e}")
        return f"📅 Google Calendar 연동이 설정되지 않아 일정을 가져올 수 없습니다. ({e})"
    
    # Calendar API 서비스
    service = build('calendar', 'v3', credentials=creds)
    
    # 한국 시간대
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    
    # 오늘 00:00 ~ 23:59
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # 일정 가져오기
    events_result = service.events().list(
        calendarId='primary',
        timeMin=today_start.isoformat(),
        timeMax=today_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        logger.info("오늘 일정 없음")
        return "📅 오늘은 예정된 일정이 없습니다."
    
    # 일정 포맷팅
    schedule_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', '제목 없음')
        location = event.get('location', '')
        
        # 시간 포맷
        if 'T' in start:  # dateTime 형식
            time_str = datetime.fromisoformat(start).strftime('%H:%M')
            if location:
                schedule_list.append(f"{time_str} - {summary} ({location})")
            else:
                schedule_list.append(f"{time_str} - {summary}")
        else:  # 종일 일정
            if location:
                schedule_list.append(f"종일 - {summary} ({location})")
            else:
                schedule_list.append(f"종일 - {summary}")
    
    result = "\n".join(schedule_list)
    logger.info(f"일정 조회 완료: {len(events)}개 항목")
    
    return result


#6. 영감을 주는 명언
@mcp.tool()
def daily_quote() -> str:
    """LLM을 사용하여 오늘의 영감을 주는 명언을 생성합니다."""
    model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
    
    chat_model = ChatOpenAI(model=model_name, temperature=0.8)
    
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 오늘 하루의 명언을 알려주고 응원하는 따뜻한 도우미입니다. "
                "다음 형식으로 출력하세요:\n\n"
                "💡 오늘의 명언\n"
                "\"[명언 내용]\" - [저자]\n\n"
                "💪 응원의 한마디\n"
                "[명언의 의미를 바탕으로 오늘 하루를 응원하는 2-3줄 메시지]\n\n"
                "진심 어린 격려와 따뜻함이 담긴 톤으로 작성하세요."
            ),
            ("human", "오늘의 명언과 응원 메시지를 알려주세요.")
        ]
    )
    
    chain = prompt | chat_model
    response = chain.invoke({})
    
    logger.info("명언 생성 완료")
    return response.content

#7. Tavily 원격 MCP 서버 기반 웹 검색 (WebResearchAgent)
_WEB_SEARCH_SYSTEM_PROMPT = """당신은 웹 검색 전문가입니다.
 
tavily_search 도구 사용 시 주의사항:
- topic 파라미터는 반드시 'general', 'news', 'finance' 중 하나만 사용하세요.
- 기술, AI, 프로그래밍 관련 질문도 topic='general'을 사용하세요.
- 최신 뉴스 검색 시에만 topic='news'를 사용하세요.
- 금융/주식 관련 검색 시에만 topic='finance'를 사용하세요.
 
[최종 출력: 사실과 의견을 분리하세요.]
'Fact:' 같은 표시 없이, 사실 정보만 보여주세요.
출처(Citation)를 함께 표시하세요.
"""
 
 
class WebResearchAgent:
    """
    MCP 기반 웹 검색 에이전트
 
    우리 mcp_server.py 가 로컬에서 검색 로직을 구현하는 대신, Tavily가 직접
    운영하는 원격 MCP 서버(mcp.tavily.com)에 '클라이언트'로 접속해서 그 서버의
    tavily_search 도구를 그대로 가져다 쓰는 방식.
    """
 
    def __init__(self):
        self.model = ChatOpenAI(model="gpt-4o")
        self.mcp_client = None
        self.agent = None
        self.initialized = False
 
    async def initialize(self) -> None:
        """MCP 클라이언트 및 에이전트 초기화 (최초 호출 시 한 번만 수행)"""
        if self.initialized:
            return
 
        if not TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY 환경 변수가 필요합니다")
 
        self.mcp_client = MultiServerMCPClient(
            {
                "tavily": {
                    "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
                    "transport": "streamable_http",
                }
            }
        )
 
        tools = await self.mcp_client.get_tools(server_name="tavily")
        logger.info(f"[WEB AGENT] [INIT] Tavily 도구 로드: {[t.name for t in tools]}")
 
        self.agent = create_agent(self.model, tools)
        self.initialized = True
        logger.info("[WEB AGENT] [INIT] 초기화 완료")
 
    async def answer(self, query: str) -> str:
        """
        질의를 받아 에이전트를 실행하고, 도구 호출 없이 최종 답변 텍스트만 반환한다.
        (mcp_server.py 의 web_search_tavily 도구가 이 메서드를 그대로 감싸서 사용)
        """
        if not self.initialized:
            await self.initialize()
 
        response = await self.agent.ainvoke(
            {
                "messages": [
                    {"role": "system", "content": _WEB_SEARCH_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ]
            }
        )
        final_message = response["messages"][-1]
        return final_message.content or "응답을 생성하지 못했습니다."
 
 
# 모듈 전역에서 한 번만 생성 -> 매 호출마다 MCP 세션을 새로 맺지 않고 재사용
_web_research_agent = WebResearchAgent()
 
 
@mcp.tool()
async def web_search_tavily(query: str) -> str:
    """
    Tavily 원격 MCP 서버(mcp.tavily.com)에 접속하는 WebResearchAgent 를 통해
    실시간 웹 검색을 수행합니다. topic(general/news/finance) 선택이나 결과
    필터링은 에이전트가 내부적으로 판단해서 처리합니다.
 
    Args:
        query: 검색할 질의문
    Returns:
        사실 정보와 출처(citation)가 포함된 답변 문자열 or 에러 메시지
    """
    if not TAVILY_API_KEY:
        return (
            "TAVILY_API_KEY 가 설정되어 있지 않습니다. "
            ".env 파일에 TAVILY_API_KEY=tvly-... 형태로 추가해주세요."
        )
 
    try:
        logger.info(f"Tavily 웹 검색 시작: {query}")
        result = await _web_research_agent.answer(query)
        logger.info("Tavily 웹 검색 완료")
        return result
 
    except Exception as e:
        error_msg = f"Tavily 웹 검색 실패: {str(e)}"
        logger.error(error_msg)
        return error_msg


# 8. 종합 브리핑
@mcp.tool()
def brief_today() -> str:
    """
    사용자의 하루 시작을 돕기 위해 날씨, 뉴스, 일정, 명언을 종합하여 전달합니다.
    
    Returns:
        브리핑 지침 문자열
    """
    return """
## 📋 오늘의 브리핑 생성 가이드

다음 순서대로 도구를 실행하고, 결과를 사용자에게 보기 좋게 정리해서 알려주세요:

### 1단계: 위치 확인
- 사용자의 위치(도시)를 파악하세요.
- 위치를 모른다면, 먼저 사용자에게 질문하세요.

### 2단계: 날씨 조회
- `get_weather(도시명)` 도구를 호출하여 날씨 정보를 가져오세요.

### 3단계: 뉴스 조회
- `get_news_headlines()` 도구를 사용하여 오늘의 주요 뉴스를 가져오세요.

### 4단계: 야구 순위
- `get_kbo_rank()` 도구를 사용하여 KBO 리그 순위를 가져오세요.

### 5단계: 일정 확인
- `today_schedule()` 도구로 오늘의 일정을 확인하세요.

### 6단계: 명언
- `daily_quote()` 도구로 오늘의 명언을 가져오세요.

### 출력 형식
결과는 다음과 같이 구성해주세요:

---

# 🌅 [사용자님]을 위한 오늘의 브리핑

## ☀️ 오늘의 날씨
[get_weather 결과]

## 📰 주요 뉴스
[get_news_headlines 결과]

## ⚾ KBO 리그 순위
[get_kbo_rank 결과를 보기 좋게 포맷팅]

## 📅 오늘의 일정
[today_schedule 결과]

## 💡 오늘의 명언
[daily_quote 결과]

---

좋은 하루 되세요! 😊
"""



if __name__ == "__main__":
    # url test
    # url = "https://quotes.toscrape.com"
    
    # result = scrape_page_text(url)
    # print(f"결과: {result}")
    #====================================================================
    # get weather test
    # city = "서울"
    
    # result = get_weather(city)
    # print(result)
    
    #=====================================================
    # get headline 뉴스 테스트
    # result = get_news_headlines()
    # lines = result.split("\n")
    
    # for line in lines:
    #     print(line)
    
    #============ kbo ===============
    # result = get_kbo_rank()
    # print(result)
    
    # =========Schedule test===============
    # result = today_schedule()
    # print(result)
    
    # ============= model test =============
    # result = daily_quote()
    # print(f"모델의 응답: {result}")
    
    # =========Google Calendar 테스트===============
    # result = today_schedule()
    # print(result)
    
    # ======== Tavily 검색 테스트 =========
    # import asyncio
    # result = asyncio.run(web_search_tavily("2022년 한국 카타르 월드컵 순위"))
    # print(result)
        
    #=========== MCP 서버 테스트 =============
    mcp.run(transport="streamable-http")

