// 개발 중 화면 요청과 API를 같은 출처로 연결한다. 배포 빌드는 FastAPI가 제공한다.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } } },
});
