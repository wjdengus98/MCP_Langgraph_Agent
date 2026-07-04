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
from typing import Optional, Literal
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
from langchain_tavily import TavilySearch
from dotenv import load_dotenv
import os

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

# Tavily 검색 도구 (langchain-tavily)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily_search_tool = (
    TavilySearch(
        max_results=10,
        include_answer=True,
        search_depth="advanced",
        exclude_domains=["youtube.com", "youtu.be"],
    )
    if TAVILY_API_KEY
    else None
)
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

#5. 일정 가져오기(Mock data -> 노션,구글 스케줄 연동(update 예정))
# @mcp.tool()
# def today_schedule() -> str:
#     """일정을 가져옵니다."""
#     events = [
#             "09:00 - 데일리 스탠드업 미팅",
#             "10:30 - LangGraph 학습 시간",
#             "13:00 - 점심 약속 (강남역)",
#             "15:00 - MCP 프로젝트 개발",
#             "18:00 - 운동 (헬스장)",
#             "20:00 - 저녁 식사"
#         ]
#     result = "\n".join([f"{event}" for event in events])
#     logger.info(f"일정 조회 완료: {len(events)}개 항목")
    
#     return result

from googleapiclient.discovery import build
from datetime import datetime
import pytz

# Google calender Test
@mcp.tool()
def today_schedule() -> str:
    """Google Calendar에서 오늘의 일정을 가져옵니다."""
    
    logger.info("Google Calendar 일정 조회 시작")
    
    # 인증
    from google_auth import get_credentials
    creds = get_credentials()
    
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

_search_cleanup_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "당신은 웹 검색 결과에서 광고, 구독 안내, 조회수, 채널 정보 같은 "
            "본문과 무관한 부가 텍스트를 제거하고 핵심 사실만 간결하게 재정리하는 "
            "편집자입니다. 각 검색 결과의 'content'를 읽고, 검색 질의와 관련된 "
            "핵심 내용만 2~3문장으로 요약하세요. 원문에 없는 내용을 추가하거나 "
            "추측하지 마세요. 관련 내용이 전혀 없는 결과는 content를 빈 문자열로 "
            "두세요.\n\n"
            "다음 JSON 형식으로만 응답하세요 (마크다운 코드블록이나 다른 텍스트 없이):\n"
            '{{"cleaned": [{{"index": 1, "content": "정리된 내용"}}, ...]}}',
        ),
        (
            "human",
            "검색 질의: {query}\n\n검색 결과:\n{raw_results}",
        ),
    ]
)

def _clean_search_results(query: str, results: list) -> list:
    """
    Tavily 검색 결과의 content를 LLM으로 한 번 더 정제한다.
    광고/구독 안내/조회수 등 부가 텍스트를 제거하고 질의와 관련된 핵심만 남긴다.
    정제 과정에서 오류가 나면, 원본 content를 그대로 사용하는 쪽으로 안전하게 폴백한다.
    """
    if not results:
        return results
 
    raw_results_text = "\n".join(
        f"{i}. {item.get('content', '')}" for i, item in enumerate(results, 1)
    )
 
    try:
        model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
        cleanup_model = ChatOpenAI(model=model_name, temperature=0)
 
        chain = _search_cleanup_prompt | cleanup_model
        response = chain.invoke({"query": query, "raw_results": raw_results_text})
 
        parsed = json.loads(response.content)
        cleaned_by_index = {
            item["index"]: item["content"] for item in parsed.get("cleaned", [])
        }
 
        for i, item in enumerate(results, 1):
            if i in cleaned_by_index:
                # LLM이 빈 문자열을 줬다면 "관련 없음" 판단이므로 제외 대상으로 표시.
                # 정제 결과가 있으면 그걸로 교체.
                item["content"] = cleaned_by_index[i].strip()
            # cleaned_by_index 에 아예 없는 인덱스(파싱 누락 등)는 원본 유지
 
        return results
 
    except Exception as e:
        # 정제 실패 시 원본 결과를 그대로 반환 (검색 자체는 실패시키지 않음)
        logger.warning(f"검색 결과 정제 실패, 원본 사용: {str(e)}")
        return results

#7. Tavily 기반 실시간 웹 검색 (langchain-tavily)
@mcp.tool()
def web_search_tavily(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> str:
    """
    langchain-tavily 의 TavilySearch 도구를 사용하여 실시간 웹 검색을 수행합니다.
    Tavily 원본 결과를 LLM으로 한 번 더 정제하여, 광고/구독 안내/조회수 같은
    부가 텍스트를 제거하고 질의와 관련된 핵심 내용만 남긴 뒤 반환합니다.
 
    Args:
        query: 검색할 질의문
        max_results: 반환할 최대 검색 결과 수 (기본값 5, 최대 10)
        topic: 검색 주제. 반드시 'general', 'news', 'finance' 중 하나만 사용.
            - 기술/AI/프로그래밍 등 일반적인 질문 -> 'general'
            - 최신 뉴스/시사 검색 -> 'news'
            - 금융/주식/시장 관련 검색 -> 'finance'
    Returns:
        검색 결과를 정리한 문자열 or 에러 메시지
    """
    if tavily_search_tool is None:
        return (
            "TAVILY_API_KEY 가 설정되어 있지 않습니다. "
            ".env 파일에 TAVILY_API_KEY=tvly-... 형태로 추가해주세요."
        )
 
    try:
        logger.info(f"Tavily 웹 검색 시작: {query} (topic={topic})")
 
        # langchain-tavily 의 TavilySearch 는 max_results를 invoke 시점에
        # 바꿀 수 없으므로(인스턴스 생성 시 고정), 받아온 결과를 잘라서 사용.
        # topic 은 invoke 시점에 지정 가능한 파라미터라 그대로 전달.
        response = tavily_search_tool.invoke({"query": query, "topic": topic})
        results = response.get("results", [])[: max(1, min(max_results, 10))]
 
        # LLM으로 한 번 더 정제 (광고/구독 안내/조회수 등 제거, 핵심만 재요약)
        results = _clean_search_results(query, results)
 
        result_lines = []
 
        # Tavily 가 생성한 요약 답변이 있으면 먼저 표시
        answer = response.get("answer")
        if answer:
            result_lines.append(f"## 📝 요약 답변\n{answer}\n")
 
        result_lines.append("## 🔎 검색 결과")
        for i, item in enumerate(results, 1):
            title = item.get("title", "제목 없음")
            url = item.get("url", "#")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            result_lines.append(f"{i}. [{title}]({url})\n   {content}")
 
        logger.info(f"Tavily 웹 검색 완료: {len(results)}개 결과")
        return "\n".join(result_lines)
 
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
    result = web_search_tavily("2022년 카타르 월드컵 순위")
    print(result)    
    #=========== MCP 서버 테스트 =============
    # mcp.run(transport="streamable-http")

