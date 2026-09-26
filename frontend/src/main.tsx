// 화면의 시작점. 게임 UI와 공통 스타일을 연결한다.
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
createRoot(document.getElementById('root')!).render(<App />);
