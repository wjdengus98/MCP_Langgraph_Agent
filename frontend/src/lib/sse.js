/**
 * fetch 응답의 ReadableStream을 SSE 이벤트 단위로 파싱하는 async generator.
 *
 * EventSource는 GET만 지원하므로 POST + multipart 요청에는 fetch로 직접
 * 스트림을 읽어야 한다. 백엔드(chat_agent.py)는 이벤트마다
 *   event: <타입>\n
 *   data: <내용>\n   (내용에 줄바꿈이 있으면 data: 라인이 반복됨)
 *   \n
 * 형태로 내려보내며, SSE 스펙대로 연속된 data: 라인은 '\n'으로 이어 붙인다.
 *
 * @param {ReadableStream<Uint8Array>} stream - response.body
 * @yields {{ event: string, data: string }}
 */
export async function* parseSSEStream(stream) {
  const reader = stream.getReader()
  const decoder = new TextDecoder('utf-8')

  let buffer = ''
  let eventType = 'message'
  let dataLines = []

  const takeEvent = () => {
    if (dataLines.length === 0 && eventType === 'message') return null
    const evt = { event: eventType, data: dataLines.join('\n') }
    eventType = 'message'
    dataLines = []
    return evt
  }

  const parseLine = (line) => {
    if (line.endsWith('\r')) line = line.slice(0, -1)

    if (line === '') return takeEvent() // 빈 줄 = 이벤트 경계
    if (line.startsWith(':')) return null // 주석 라인

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') eventType = value
    else if (field === 'data') dataLines.push(value)
    // id, retry 등 다른 필드는 이 백엔드에서 사용하지 않는다.
    return null
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let idx
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 1)
        const evt = parseLine(line)
        if (evt) yield evt
      }
    }

    // 스트림 종료: 멀티바이트 잔여분 + 개행 없이 끝난 마지막 라인 처리
    buffer += decoder.decode()
    if (buffer.length > 0) {
      const evt = parseLine(buffer)
      if (evt) yield evt
    }
    const tail = takeEvent()
    if (tail) yield tail
  } finally {
    reader.releaseLock()
  }
}
