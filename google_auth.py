#Google calender 인증
import os
from google.auth.transport.requests import Request # 토큰 갱신용
from google.oauth2.credentials import Credentials # 인증 객체 생성
from google_auth_oauthlib.flow import InstalledAppFlow # OAuth 인증 흐름 관리 (브라우저 열기)

# 캘린더 읽기 전용 권한
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_credentials():
    """Google Calender 인증 정보 가져오기"""
    creds = None
    
    if os.path.exists('token.json'): #token.json이 존재하는 경우 
        creds = Credentials.from_authorized_user_file('token.json', SCOPES) #파일에서 인증 정보 로딩
    
    if not creds or not creds.valid: # 토큰이 없거나 유효하지 않은 경우
        if creds and creds.expired and creds.refresh_token: # 만료된 경우
            creds.refresh(Request()) # refresh_token을 사용하여 자동 갱신
        else: # 없는경우 
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES) # # credentials.json 파일에서 OAuth 설정 읽기
            creds = flow.run_local_server(port=0) #브라우저 열어서 로그인 권한 승인
        
        # 파일 저장하기 
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

if __name__ == "__main__":
    print("google calender 인증 시작")
    credss =get_credentials()
    print("인증 성공: token.json 생성 완료")