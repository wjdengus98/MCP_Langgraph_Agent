import { useEffect, useRef, useState } from 'react'
import Composer from './components/Composer.jsx'
import Message from './components/Message.jsx'
import Welcome from './components/Welcome.jsx'
import { SparkIcon } from './components/Icons.jsx'
import { parseSSEStream } from './lib/sse.js'

// 배포 시에는 백엔드(chat_agent.py)가 프론트엔드를 같은 도메인에서 서빙하므로
// 상대 경로를 쓰고, 로컬 개발 시에는 vite.config.js의 프록시가 8001로 전달한다.
const API_URL = import.meta.env.VITE_API_URL || '/chat'

const genSessionId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `session-${Date.now()}-${Math.random().toString(16).slice(2)}`

let seq = 0
const uid = () => ++seq

export default function App() {
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)

  const sessionRef = useRef(genSessionId())
  const abortRef = useRef(null)
  const scrollRef = useRef(null)
  // 사용자가 바닥 근처에 있을 때만 새 청크를 따라 자동 스크롤한다.
  const stickToBottomRef = useRef(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottomRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  // 스트리밍 중에는 입력이 막혀 있어 마지막 메시지가 항상 현재 어시스턴트 메시지다.
  const updateLast = (updater) => {
    setMessages((prev) => {
      const next = prev.slice()
      next[next.length - 1] = updater(next[next.length - 1])
      return next
    })
  }

  const send = async (text) => {
    if (streaming) return

    setMessages((prev) => [
      ...prev,
      { id: uid(), role: 'user', content: text },
      { id: uid(), role: 'assistant', content: '', tools: [], error: null, aborted: false },
    ])
    setStreaming(true)
    stickToBottomRef.current = true

    const controller = new AbortController()
    abortRef.current = controller

    const form = new FormData()
    form.append('message', text)
    form.append('session_id', sessionRef.current)

    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        body: form,
        signal: controller.signal,
      })

      const ctype = res.headers.get('content-type') || ''
      if (!res.ok) throw new Error(`서버 오류가 발생했습니다. (HTTP ${res.status})`)
      if (ctype.includes('application/json')) {
        // 에이전트 미준비 시 백엔드가 SSE 대신 JSON({"error": ...})을 반환한다.
        const body = await res.json()
        throw new Error(body.error || '서버가 스트리밍 응답을 반환하지 않았습니다.')
      }
      if (!res.body) throw new Error('서버 응답 스트림을 열 수 없습니다.')

      for await (const evt of parseSSEStream(res.body)) {
        if (evt.event === 'text') {
          updateLast((m) => ({ ...m, content: m.content + evt.data }))
        } else if (evt.event === 'tool_start') {
          updateLast((m) => ({
            ...m,
            tools: [...m.tools, { id: uid(), name: evt.data, done: false }],
          }))
        } else if (evt.event === 'tool_end') {
          // 백엔드가 tool_end에 도구명을 싣지 않으므로, 가장 먼저 시작된
          // 미완료 도구를 완료 처리한다(도구는 사실상 순차 실행).
          updateLast((m) => {
            const tools = m.tools.slice()
            const idx = tools.findIndex((t) => !t.done)
            if (idx !== -1) tools[idx] = { ...tools[idx], done: true }
            return { ...m, tools }
          })
        } else if (evt.event === 'error') {
          updateLast((m) => ({ ...m, error: evt.data }))
        }
      }

      // 정상 종료: 남은 도구 표시를 정리하고, 아무것도 못 받았으면 안내한다.
      updateLast((m) => ({
        ...m,
        tools: m.tools.map((t) => (t.done ? t : { ...t, done: true })),
        error:
          m.error || (m.content ? null : '응답이 수신되지 않았습니다. 잠시 후 다시 시도해주세요.'),
      }))
    } catch (err) {
      if (err.name === 'AbortError') {
        updateLast((m) => ({
          ...m,
          aborted: true,
          tools: m.tools.map((t) => (t.done ? t : { ...t, done: true })),
        }))
      } else {
        const message =
          err instanceof TypeError
            ? '서버에 연결할 수 없습니다. 백엔드 서버가 실행 중인지 확인해주세요.'
            : err.message
        updateLast((m) => ({ ...m, error: message }))
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  const stop = () => abortRef.current?.abort()

  const resetChat = () => {
    abortRef.current?.abort()
    sessionRef.current = genSessionId()
    setMessages([])
    stickToBottomRef.current = true
  }

  const lastIndex = messages.length - 1

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <div className="brand-logo">
              <SparkIcon size={17} />
            </div>
            <div>
              <div className="brand-name">세이넌</div>
              <div className="brand-sub">
                <span className="status-dot" />
                온라인 · MCP Agent
              </div>
            </div>
          </div>
          {messages.length > 0 && (
            <button className="ghost-btn" onClick={resetChat}>
              새 대화
            </button>
          )}
        </div>
      </header>

      <main className="chat" ref={scrollRef} onScroll={handleScroll}>
        <div className="chat-inner">
          {messages.length === 0 ? (
            <Welcome onPick={send} />
          ) : (
            messages.map((msg, i) => (
              <Message
                key={msg.id}
                msg={msg}
                isStreaming={streaming && i === lastIndex && msg.role === 'assistant'}
              />
            ))
          )}
        </div>
      </main>

      <Composer onSend={send} onStop={stop} streaming={streaming} />
    </div>
  )
}
