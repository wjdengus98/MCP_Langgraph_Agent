import { useRef, useState } from 'react'
import { SendIcon, StopIcon } from './Icons.jsx'

const MAX_HEIGHT = 160

export default function Composer({ onSend, onStop, streaming }) {
  const taRef = useRef(null)
  const [hasText, setHasText] = useState(false)

  const resize = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, MAX_HEIGHT) + 'px'
  }

  const handleInput = () => {
    resize()
    setHasText(taRef.current.value.trim().length > 0)
  }

  const submit = () => {
    const ta = taRef.current
    const text = ta.value.trim()
    if (!text || streaming) return
    onSend(text)
    ta.value = ''
    setHasText(false)
    resize()
    ta.focus()
  }

  const handleKeyDown = (e) => {
    // 한글 IME 조합 중 Enter는 무시해야 마지막 글자가 중복 전송되지 않는다.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <footer className="composer-wrap">
      <div className="composer">
        <textarea
          ref={taRef}
          rows={1}
          placeholder="무엇이든 물어보세요…"
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          aria-label="메시지 입력"
          autoFocus
        />
        {streaming ? (
          <button className="send-btn stop" onClick={onStop} title="응답 중지" aria-label="응답 중지">
            <StopIcon />
          </button>
        ) : (
          <button
            className="send-btn"
            onClick={submit}
            disabled={!hasText}
            title="전송"
            aria-label="전송"
          >
            <SendIcon />
          </button>
        )}
      </div>
      <p className="composer-hint">Enter 전송 · Shift + Enter 줄바꿈</p>
    </footer>
  )
}
