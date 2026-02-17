"""
MCP Server - AI Agent를 위한 도구 모음

제공하는 도구:
1. scrape_page_text: 웹페이지 텍스트 스크래핑
2. get_weather: 도시별 날씨 조회
3. get_news_headlines: 구글 RSS 뉴스 헤드라인
4. get_kbo_rank: KBO 프로야구 순위
5. today_schedule: 오늘의 일정 (Mock 데이터)
6. daily_quote: 영감을 주는 명언 생성
7. brief_today: 종합 브리핑 오케스트레이터
"""

import json
import logging
from typing import Optional
import feedparser
import httpx
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from mcp.server.fastmcp import FastMCP
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from tenacity import retry, stop_after_attempt, wait_exponential
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
        
if __name__ == "__main__":
    # url test
    # url = "https://quotes.toscrape.com"
    
    # result = scrape_page_text(url)
    # print(f"결과: {result}")
    #====================================================================
    # get weather test
    city = "서울"
    
    result = get_weather(city)
    print(result)

