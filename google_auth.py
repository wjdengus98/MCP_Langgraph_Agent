#Google calender 인증
import json
import os
from google.auth.transport.requests import Request # 토큰 갱신용
from google.oauth2.credentials import Credentials # 인증 객체 생성
from google_auth_oauthlib.flow import InstalledAppFlow # OAuth 인증 흐름 관리 (브라우저 열기)

# 캘린더 읽기 전용 권한
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_credentials():
    """Google Calender 인증 정보 가져오기

    인증 정보를 찾는 순서:
    1. GOOGLE_TOKEN_JSON 환경 변수 (배포 환경용 - token.json 파일 내용을 그대로 넣음)
    2. token.json 파일 (로컬)
    3. credentials.json + 브라우저 OAuth 흐름 (로컬 최초 인증)

    서버(배포) 환경에서는 브라우저를 열 수 없으므로, 1번이 없으면 에러를 발생시킨다.
    """
    creds = None

    token_json = os.getenv('GOOGLE_TOKEN_JSON')
    if token_json: # 배포 환경: 환경 변수에서 토큰 로딩
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif os.path.exists('token.json'): #token.json이 존재하는 경우
        creds = Credentials.from_authorized_user_file('token.json', SCOPES) #파일에서 인증 정보 로딩

    if not creds or not creds.valid: # 토큰이 없거나 유효하지 않은 경우
        if creds and creds.expired and creds.refresh_token: # 만료된 경우
            creds.refresh(Request()) # refresh_token을 사용하여 자동 갱신
        elif os.path.exists('credentials.json'): # 로컬: 브라우저 열어서 최초 인증
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES) # # credentials.json 파일에서 OAuth 설정 읽기
            creds = flow.run_local_server(port=0) #브라우저 열어서 로그인 권한 승인
        else: # 서버 환경인데 토큰도 없는 경우
            raise RuntimeError(
                "Google Calendar 인증 정보가 없습니다. "
                "로컬에서 google_auth.py를 실행해 token.json을 만든 뒤, "
                "그 내용을 GOOGLE_TOKEN_JSON 환경 변수로 설정해주세요."
            )

        # 파일 저장하기 (환경 변수 기반 인증이면 파일로 저장하지 않음)
        if not token_json:
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

    return creds

if __name__ == "__main__":
    print("google calender 인증 시작")
    credss =get_credentials()
    print("인증 성공: token.json 생성 완료")
