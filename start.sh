#!/usr/bin/env bash
# 컨테이너 안에서 MCP 서버(8000)를 먼저 띄우고, 준비되면 채팅 서버를 시작한다.
set -e

python mcp_server.py &
MCP_PID=$!

# MCP 서버(8000 포트)가 열릴 때까지 대기 (최대 30초)
for i in $(seq 1 30); do
    if python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 1)" 2>/dev/null; then
        echo "MCP 서버 준비 완료 (${i}초)"
        break
    fi
    if ! kill -0 "$MCP_PID" 2>/dev/null; then
        echo "MCP 서버가 시작 중에 종료되었습니다." >&2
        exit 1
    fi
    sleep 1
done

# 채팅 서버를 메인 프로세스로 실행 (종료 시 컨테이너와 함께 MCP 서버도 정리됨)
exec uvicorn chat_agent:app --host 0.0.0.0 --port "${PORT:-8001}"
