import { SparkIcon } from './Icons.jsx'

const SUGGESTIONS = [
  { icon: '🌤️', label: '서울 날씨 어때?' },
  { icon: '☀️', label: '오늘 하루 브리핑해줘' },
  { icon: '⚾', label: '프로야구 순위 보여줘' },
  { icon: '📰', label: '최신 뉴스 알려줘' },
]

export default function Welcome({ onPick }) {
  return (
    <div className="welcome">
      <div className="welcome-logo">
        <SparkIcon size={28} />
      </div>
      <h1>
        안녕하세요, <span className="grad-text">세이넌</span>이에요
      </h1>
      <p>날씨 · 뉴스 · 일정 · 프로야구 순위까지, 무엇이든 물어보세요.</p>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s.label} onClick={() => onPick(s.label)}>
            <span className="s-icon">{s.icon}</span>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  )
}
