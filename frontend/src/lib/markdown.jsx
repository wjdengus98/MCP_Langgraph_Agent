/**
 * 답변 텍스트용 경량 인라인 마크다운 렌더러.
 *
 * dangerouslySetInnerHTML 없이 React 엘리먼트로 변환하며,
 * [제목](URL) 링크 · **굵게** · `코드` · 맨몸 URL 자동 링크를 지원한다.
 * href는 http(s)만 허용되므로 javascript: 류 주입이 불가능하다.
 * 줄바꿈은 CSS(white-space: pre-wrap)가 처리한다.
 */

const INLINE_RE =
  /`([^`\n]+)`|\[([^\]\n]*)\]\((https?:\/\/[^\s)]+)\)|\*\*([^\n]+?)\*\*|(https?:\/\/[^\s<>"'`)\]]+)/g

function Link({ href, children }) {
  return (
    <a className="md-link" href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

export function renderInline(text, keyPrefix = 'md') {
  if (!text) return null

  const nodes = []
  const re = new RegExp(INLINE_RE.source, 'g')
  let lastIndex = 0
  let i = 0
  let m

  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIndex) nodes.push(text.slice(lastIndex, m.index))
    const key = `${keyPrefix}-${i++}`

    if (m[1] !== undefined) {
      // `인라인 코드`
      nodes.push(
        <code className="md-code" key={key}>
          {m[1]}
        </code>,
      )
    } else if (m[3] !== undefined) {
      // [제목](URL)
      nodes.push(
        <Link href={m[3]} key={key}>
          {m[2] || m[3]}
        </Link>,
      )
    } else if (m[4] !== undefined) {
      // **굵게** (내부에 링크가 있을 수 있어 재귀 렌더링)
      nodes.push(<strong key={key}>{renderInline(m[4], key)}</strong>)
    } else if (m[5] !== undefined) {
      // 맨몸 URL — 문장 끝 구두점은 링크에서 제외
      let url = m[5]
      const trail = url.match(/[.,!?;:]+$/)
      let after = ''
      if (trail) {
        after = trail[0]
        url = url.slice(0, url.length - after.length)
      }
      nodes.push(
        <Link href={url} key={key}>
          {url}
        </Link>,
      )
      if (after) nodes.push(after)
    }

    lastIndex = re.lastIndex
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}
