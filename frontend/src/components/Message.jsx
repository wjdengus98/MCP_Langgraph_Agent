import { renderInline } from '../lib/markdown.jsx'
import { SparkIcon, CheckIcon, SpinnerIcon } from './Icons.jsx'

function ToolChip({ tool }) {
  return (
    <span className={`tool-chip ${tool.done ? 'done' : 'running'}`}>
      {tool.done ? <CheckIcon /> : <SpinnerIcon />}
      <span className="tool-name">{tool.name}</span>
      {!tool.done && <span className="tool-status">실행 중…</span>}
    </span>
  )
}

function TypingDots() {
  return (
    <span className="typing-dots" aria-label="응답 생성 중">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
    </span>
  )
}

export default function Message({ msg, isStreaming }) {
  if (msg.role === 'user') {
    return (
      <div className="row user">
        <div className="stack">
          <div className="bubble">{msg.content}</div>
        </div>
      </div>
    )
  }

  const showTyping = isStreaming && !msg.content && !msg.error

  return (
    <div className="row assistant">
      <div className="avatar">
        <SparkIcon />
      </div>
      <div className="stack">
        {msg.tools.length > 0 && (
          <div className="tool-row">
            {msg.tools.map((t) => (
              <ToolChip key={t.id} tool={t} />
            ))}
          </div>
        )}
        {msg.content && (
          <div className="bubble">
            {renderInline(msg.content, `m${msg.id}`)}
            {isStreaming && <span className="caret" />}
          </div>
        )}
        {showTyping && (
          <div className="bubble typing">
            <TypingDots />
          </div>
        )}
        {msg.error && (
          <div className="error-bubble">
            <span className="error-mark">!</span>
            <span>{msg.error}</span>
          </div>
        )}
        {msg.aborted && <div className="aborted-note">응답이 중지되었습니다.</div>}
      </div>
    </div>
  )
}
