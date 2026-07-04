import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 백엔드(chat_agent.py)의 CORS 허용 목록이 http://localhost:5173 고정이므로
// 포트가 밀리면 조용히 5174로 뜨지 않도록 strictPort를 켠다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
