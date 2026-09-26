// 로컬 화면 검사 전용. 운영 API 대신 TEST ONLY 자료를 넣으며 실제 DB에는 요청하지 않습니다.
// 실행: node scripts/check_ui.mjs (Node 24, 설치된 Chrome 필요)
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'test-results');
const profile = path.join(output, `ui-profile-${Date.now()}-${process.pid}`);
const baseUrl = new URL(process.env.UI_BASE_URL || 'http://localhost:8000');
assert(['localhost', '127.0.0.1', '[::1]'].includes(baseUrl.hostname), '로컬 개발 주소만 검사합니다.');
const chromePath = process.env.CHROME_PATH || (process.platform === 'win32'
  ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  : process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'google-chrome');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const summary = {
  test_only: true,
  limitation: '브라우저 화면·입력 동작 검사입니다. 점수와 기록은 검사 전용 자료이며 실제 모델·DB 검증 결과가 아닙니다.',
  started_at: new Date().toISOString(),
  base_url: baseUrl.origin,
  checks: [], screenshots: [], browser_errors: [], viewport_samples: [], passed: false,
};
let chrome;
let chromeExited = false;
let profileCreated = false;
let spawnError;
let stderr = '';
let socket;
let sequence = 0;
let requestedViewport;
const pending = new Map();

// 문서의 첫 스크립트보다 먼저 설치합니다. 알 수 없는 /api 요청도 서버로 보내지 않습니다.
function installFixture() {
  const originalFetch = window.fetch.bind(window);
  // UI 모형 검사에서는 실시간 연결도 실제 서버로 보내지 않습니다.
  window.EventSource = class extends EventTarget {
    static CONNECTING = 0; static OPEN = 1; static CLOSED = 2;
    readyState = 1; onopen = null; onerror = null; onmessage = null;
    constructor(url) { super(); this.url = url; queueMicrotask(() => { const event = new Event('open'); this.onopen?.(event); this.dispatchEvent(event); }); }
    close() { this.readyState = 2; }
  };
  // 기기 날짜와 다른 서버 날짜를 보내 날짜 표시가 서버 응답을 따르는지 확인합니다.
  const day = '2031-12-31';
  const now = '2031-12-31T14:47:26.000Z';
  const words = ['산책', '여행', '바다', '하늘', '바람', '책', '나무'];
  // 아래 점수·순위는 경계 표시 검사용 자료입니다. null 두 개는 1,001위부터의 범위 밖을 뜻합니다.
  const scores = [88.1234, 24.5, 12.25, 45.6789, 45.6789, 45.6789, 1.2];
  const wordRanks = [1, 1000, null, 250, 750, 500, null];
  const state = {
    server_now: now, puzzle_date: day, yesterday_answer: '겨울', next_reset_at: '2031-12-31T15:00:00.000Z',
    user: { id: 'ui-test-me', nickname: 'UI검사중' },
    model: { ready: true, name: 'TEST ONLY UI fixture', error: null, scores_updated_at: null },
    similarity_reference: { ready: true, error: null, vocabulary_size: 49485, top1: 88.1234, top10: 79.5678, top1000: 24.5 },
    game: {
      status: 'playing', started_at: new Date(Date.parse(now) - 754000).toISOString(), completed_at: null,
      elapsed_ms: 754000, attempts: 7,
      guesses: words.map((word, index) => ({ word, similarity: scores[index], similarity_rank: wordRanks[index], attempt: 7 - index, is_correct: false })),
    },
    ranking: {
      completed: [
        { user_id: 'ui-test-one', nickname: '검사완료하나', attempts: 8, elapsed_ms: 93400, rank: 1, is_me: false, best_similarity: 100, best_similarity_rank: 0 },
        { user_id: 'ui-test-two', nickname: '검사완료둘', attempts: 8, elapsed_ms: 93400, rank: 1, is_me: false, best_similarity: 100, best_similarity_rank: 0 },
        { user_id: 'ui-test-three', nickname: '같은횟수다른순위', attempts: 8, elapsed_ms: 120000, rank: 3, is_me: false, best_similarity: 100, best_similarity_rank: 0 },
        { user_id: 'ui-test-four', nickname: '단독순위', attempts: 9, elapsed_ms: 150000, rank: 4, is_me: false, best_similarity: 100, best_similarity_rank: 0 },
      ],
      playing: [{ user_id: 'ui-test-me', nickname: 'UI검사중', attempts: 7, elapsed_ms: null, rank: null, is_me: true, best_similarity: 88.1234, best_similarity_rank: 1 }],
    },
  };
  const fixture = { test_only: true, requests: [], state, today_answer: '달빛', rolloverAfterNextStateRead: null, rolloverAfterNextGuess: null };
  window.__GANMANTLE_UI_TEST__ = fixture;
  const response = (body, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
    if (url.pathname !== '/api' && !url.pathname.startsWith('/api/')) return originalFetch(input, init);
    const method = init.method || (input instanceof Request ? input.method : 'GET');
    fixture.requests.push({ path: url.pathname, method });
    if (url.pathname === '/api/chat/rooms') return response({ rooms: [{ id: '00000000-0000-0000-0000-000000000001', kind: 'global', name: '전체 대화', owner_id: null }], invitations: [] });
    if (/^\/api\/chat\/rooms\/[^/]+\/messages$/.test(url.pathname) && method === 'GET') return response({ messages: [], next_before: null });
    if (url.pathname === '/api/state' && method === 'GET') {
      const snapshot = response(state);
      // 첫 응답은 자정 직전, 다음 자동 조회부터는 새 날짜를 돌려주는 검사 전용 전환입니다.
      if (fixture.rolloverAfterNextStateRead) {
        Object.assign(state, fixture.rolloverAfterNextStateRead);
        fixture.rolloverAfterNextStateRead = null;
      }
      return snapshot;
    }
    if (url.pathname === '/api/guesses' && method === 'POST') {
      const body = JSON.parse(init.body || '{}');
      if (body.word === '아무거나ㅏㅣㅓ') return response({ detail: {
        code: 'invalid_word', message: '입력할 수 없는 단어예요. 공백 없이 완성된 한글 단어를 입력해 주세요.',
      } }, 400);
      const duplicateIndex = state.game.guesses.findIndex(item => item.word === body.word);
      if (duplicateIndex >= 0) {
        state.game.guesses.unshift(...state.game.guesses.splice(duplicateIndex, 1));
        if (fixture.rolloverAfterNextGuess) {
          Object.assign(state, fixture.rolloverAfterNextGuess);
          fixture.rolloverAfterNextGuess = null;
          return response({ ...state, duplicate: true, date_changed: true });
        }
        return response({ ...state, duplicate: true });
      }
      if (body.word !== '사과') return response({ detail: { code: 'ui_test_only', message: 'UI 검사에서 허용하지 않은 요청입니다.' } }, 400);
      const attempt = ++state.game.attempts;
      state.game.guesses.unshift({ word: body.word, similarity: 61.25, similarity_rank: 42, attempt, is_correct: false });
      state.ranking.playing[0].attempts = attempt;
      return response({ ...state, duplicate: false });
    }
    return response({ detail: { code: 'ui_test_blocked', message: '실제 API 요청은 UI 검사에서 차단됩니다.' } }, 500);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('div');
    banner.textContent = 'TEST ONLY · UI fixture · 실제 게임 기록 아님';
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:10000;text-align:center;background:#fff2ce;color:#5f4800;font:11px/20px sans-serif;pointer-events:none';
    banner.id = 'ui-test-only-banner';
    document.body.append(banner);
  }, { once: true });
}

function command(method, params = {}, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP 시간 초과: ${method}`)); }, timeout);
    pending.set(id, { resolve, reject, timer });
    try { socket.send(JSON.stringify({ id, method, params })); }
    catch (error) { clearTimeout(timer); pending.delete(id); reject(error); }
  });
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
async function until(expression, label, milliseconds = 10000) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    try { if (await evaluate(expression)) return; } catch (error) {
      if (!/context|navigat/i.test(error.message)) throw error;
    }
    await sleep(100);
  }
  throw new Error(`화면 대기 시간 초과: ${label}`);
}
async function check(name, callback) {
  try { const details = await callback(); summary.checks.push({ name, passed: true, ...(details ? { details } : {}) }); }
  catch (error) { summary.checks.push({ name, passed: false, error: error.message }); throw error; }
}
async function screenshot(filename) {
  const result = await command('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false });
  const png = Buffer.from(result.data, 'base64');
  const pixels = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
  assert.equal(pixels.width, requestedViewport.width, '캡처 너비가 요청한 화면 너비와 다릅니다.');
  assert.equal(pixels.height, requestedViewport.height, '캡처 높이가 요청한 화면 높이와 다릅니다.');
  await writeFile(path.join(output, filename), png);
  summary.screenshots.push({ path: `test-results/${filename}`, test_only: true, pixels });
}
async function loadViewport(width, height, mobile) {
  // 이전 화면의 입력 포커스·이동 위치·확대율이 다음 기기 검사에 남지 않도록 먼저 빈 문서로 이동합니다.
  await command('Page.navigate', { url: 'about:blank' });
  await until('location.href === "about:blank" && document.readyState === "complete"', '이전 문서 해제');
  await command('Page.resetNavigationHistory');
  await command('Emulation.clearDeviceMetricsOverride');
  await command('Emulation.resetPageScaleFactor');
  requestedViewport = { width, height, mobile };
  await command('Emulation.setDeviceMetricsOverride', { width, height, screenWidth: width, screenHeight: height, deviceScaleFactor: 1, mobile });
  await command('Emulation.setPageScaleFactor', { pageScaleFactor: 1 });
  await command('Page.navigate', { url: baseUrl.href });
  await until('window.__GANMANTLE_UI_TEST__?.test_only && !!document.querySelector("#guess:not(:disabled)")', '게임 입력 준비');
  await evaluate('document.fonts.ready.then(() => true)');
  await settleFrame();
  summary.viewport_samples.push({ phase: 'before-chat', requested: requestedViewport, ...await viewportMetrics() });
}
async function setWord(word) {
  await evaluate(`(() => {
    const input = document.querySelector('#guess');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(word)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
  await until('!document.querySelector(".guess-form button").disabled', '제출 버튼 활성화');
  await evaluate('document.querySelector(".guess-form").requestSubmit()');
}
async function openChat() {
  await evaluate('document.querySelector(".chat-toggle").click()');
  await until('!!document.querySelector(".chat-panel")', '채팅 열기');
  await settleFrame();
}
async function settleFrame() {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
}
async function viewportMetrics() {
  return evaluate(`(() => {
    const v = visualViewport;
    return { width: innerWidth, height: innerHeight, scrollX, scrollY,
      documentWidth: document.documentElement.scrollWidth, documentClientWidth: document.documentElement.clientWidth,
      bodyWidth: document.body.scrollWidth, bodyClientWidth: document.body.clientWidth,
      screenWidth: screen.width, screenHeight: screen.height,
      visual: v && { width: v.width, height: v.height, scale: v.scale, offsetLeft: v.offsetLeft, offsetTop: v.offsetTop, pageLeft: v.pageLeft, pageTop: v.pageTop },
      activeElement: document.activeElement?.id || document.activeElement?.className,
      outsideElements: [...document.querySelectorAll('body *')].filter(el => {
        const rect = el.getBoundingClientRect();
        return !el.closest('.guess-table-wrap, .ranking-table-wrap') && (rect.right > ${requestedViewport.width} + 1 || rect.left < -1);
      }).slice(0, 20).map(el => ({ tag: el.tagName, id: el.id, className: el.className, left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right, position: getComputedStyle(el).position })) };
  })()`);
}
async function layout(mobile) {
  const sizes = await evaluate(`(() => {
    const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
    return { width: innerWidth, height: innerHeight, documentWidth: document.documentElement.scrollWidth,
      game: box('.game-card'), guess: box('#guess'), dialog: box('.chat-panel'), close: box('.chat-close'), chatInput: box('#chat-message'),
      tables: [...document.querySelectorAll('.guess-table-wrap, .ranking-table-wrap')].map(el => ({ width: el.clientWidth, contentWidth: el.scrollWidth, overflow: getComputedStyle(el).overflowX, left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right })) };
  })()`);
  const viewport = await viewportMetrics();
  summary.viewport_samples.push({ phase: 'chat-open', requested: requestedViewport, ...viewport });
  const { width, height } = requestedViewport;
  assert(Math.abs(viewport.width - width) <= 1, `innerWidth ${viewport.width}가 요청 너비 ${width}와 다릅니다.`);
  assert(Math.abs(viewport.height - height) <= 1, `innerHeight ${viewport.height}가 요청 높이 ${height}와 다릅니다.`);
  assert(viewport.documentWidth <= width + 1 && viewport.bodyWidth <= width + 1, '문서 또는 body가 요청한 화면 너비를 벗어납니다.');
  assert(Math.abs(viewport.scrollX) <= 1 && Math.abs(viewport.scrollY) <= 1, '채팅 포커스가 페이지를 자동으로 이동시켰습니다.');
  assert(Math.abs(viewport.visual.scale - 1) <= 0.01, '모바일 화면이 확대되거나 축소되었습니다.');
  assert(Math.abs(viewport.visual.offsetLeft) <= 1 && Math.abs(viewport.visual.offsetTop) <= 1, '시각 뷰포트가 화면 시작점에서 이동했습니다.');
  if (mobile) {
    assert(Math.abs(viewport.documentClientWidth - width) <= 1, '모바일 문서 기준 너비가 다릅니다.');
    assert(Math.abs(viewport.visual.width - width) <= 1 && Math.abs(viewport.visual.height - height) <= 1, '모바일 시각 뷰포트 크기가 요청과 다릅니다.');
  }
  for (const key of ['guess', 'dialog', 'close', 'chatInput']) {
    const item = sizes[key];
    assert(item.width > 0 && item.height > 0, `${key}가 보이지 않습니다.`);
    assert(item.left >= -1 && item.right <= width + 1, `${key}가 요청한 화면 너비를 벗어납니다.`);
    assert(item.top >= -1 && item.bottom <= height + 1, `${key}가 요청한 화면 높이를 벗어납니다.`);
  }
  for (const table of sizes.tables) {
    assert(table.left >= -1 && table.right <= width + 1, '표 스크롤 영역이 요청한 화면을 벗어납니다.');
    if (mobile) assert(table.contentWidth > table.width && ['auto', 'scroll'].includes(table.overflow), '모바일 표는 카드 안에서만 가로로 스크롤해야 합니다.');
  }
  return { ...sizes, viewport };
}

async function assertGuessOrder(latest, previous, attempts) {
  const rows = await evaluate(`[...document.querySelectorAll('.guess-table tbody tr')].map(row => ({
    word: row.querySelector('.guess-word')?.firstChild.textContent,
    attempt: Number(row.querySelector('.attempt')?.textContent),
    score: row.querySelector('.score')?.textContent,
    section: row.parentElement.className,
  }))`);
  assert.equal(await evaluate('document.querySelectorAll(".latest-guess tr").length'), 1, '최근 입력은 독립된 한 행이어야 합니다.');
  assert.deepEqual(rows.map(row => row.word), [latest, ...previous]);
  assert.equal(rows[0].section, 'latest-guess');
  assert(rows.slice(1).every(row => row.section === 'previous-guesses'));
  assert.equal(new Set(rows.map(row => row.word)).size, attempts, '같은 단어가 최근 행과 과거 행에 중복됐습니다.');
  assert.equal(rows.length, attempts);
  assert.equal(await evaluate('Number(document.querySelector(".game-summary strong").textContent)'), attempts);
  const firstAttempts = { 산책: 7, 여행: 6, 바다: 5, 하늘: 4, 바람: 3, 책: 2, 나무: 1, 사과: 8 };
  for (const row of rows) assert.equal(row.attempt, firstAttempts[row.word], `${row.word}의 최초 시도 번호가 바뀌었습니다.`);
  return rows;
}

async function referenceLayout(mobile) {
  const boxes = await evaluate(`(() => {
    const box = el => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
    return { container: box(document.querySelector('.similarity-reference')), title: box(document.querySelector('.reference-title')),
      items: [...document.querySelectorAll('.reference-item')].map(el => ({ ...box(el), label: box(el.querySelector('span')), score: box(el.querySelector('strong')) })) };
  })()`);
  const inside = (item, bounds, label) => {
    assert(item.width > 0 && item.height > 0, `${label}가 보이지 않습니다.`);
    assert(item.left >= bounds.left - 1 && item.right <= bounds.right + 1 && item.top >= bounds.top - 1 && item.bottom <= bounds.bottom + 1, `${label}가 영역 밖으로 잘렸습니다.`);
  };
  inside(boxes.container, { left: 0, top: 0, right: requestedViewport.width, bottom: requestedViewport.height }, '기준 유사도');
  inside(boxes.title, boxes.container, '기준 유사도 제목');
  assert.equal(boxes.items.length, 3);
  assert(Math.max(...boxes.items.map(item => item.width)) - Math.min(...boxes.items.map(item => item.width)) <= 1, '세 기준값 그룹의 너비가 다릅니다.');
  for (const [index, item] of boxes.items.entries()) {
    inside(item, boxes.container, `기준값 그룹 ${index + 1}`);
    inside(item.label, item, `순위 이름 ${index + 1}`);
    inside(item.score, item, `점수 ${index + 1}`);
    if (index) assert(boxes.items[index - 1].right <= item.left + 1, '기준값 그룹이 서로 겹칩니다.');
    if (mobile) {
      assert(boxes.title.bottom <= item.top + 1, '모바일 제목과 기준값이 겹칩니다.');
      assert(item.label.bottom <= item.score.top + 1, '모바일 순위 이름과 점수가 겹칩니다.');
    } else {
      assert(boxes.title.right <= item.left + 1, '제목은 기준값 왼쪽에 있어야 합니다.');
      assert(Math.abs((boxes.title.top + boxes.title.bottom) / 2 - (item.top + item.bottom) / 2) <= 1, '데스크톱 기준값은 한 줄이어야 합니다.');
      assert(item.label.right <= item.score.left + 1, '순위 이름과 점수가 겹칩니다.');
    }
  }
  const viewport = await viewportMetrics();
  assert(Math.abs(viewport.width - requestedViewport.width) <= 1 && viewport.documentWidth <= requestedViewport.width + 1 && viewport.bodyWidth <= requestedViewport.width + 1, '기준 유사도가 전체 화면 너비를 늘렸습니다.');
  return { ...boxes, requested: requestedViewport };
}

try {
  await mkdir(output, { recursive: true });
  await mkdir(profile); // 기존 폴더를 재사용하지 않아 이번 실행의 소유권을 확인합니다.
  profileCreated = true;
  chrome = spawn(chromePath, [
    '--headless=new', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-sync', '--window-size=1600,1500', 'about:blank',
  ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  chrome.on('error', error => { spawnError = error; });
  chrome.on('exit', () => { chromeExited = true; });
  chrome.stderr.on('data', data => { stderr = (stderr + data.toString()).slice(-4000); });
  let port;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (spawnError) throw spawnError;
    if (chromeExited) throw new Error(`검사용 Chrome이 종료되었습니다. ${stderr}`);
    try { port = Number((await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); if (port) break; }
    // Windows에서는 Chrome이 파일을 쓰는 순간 잠깐 잠길 수 있습니다.
    catch (error) { if (!['ENOENT', 'EBUSY'].includes(error.code)) throw error; }
    await sleep(100);
  }
  assert(port, '30초 안에 Chrome 검사 포트를 찾지 못했습니다.');
  const pages = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(3000) }).then(response => response.json());
  const page = pages.find(item => item.type === 'page');
  assert(page?.webSocketDebuggerUrl, '검사용 브라우저 탭을 찾지 못했습니다.');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const item = pending.get(message.id);
      if (!item) return;
      clearTimeout(item.timer); pending.delete(message.id);
      if (message.error) item.reject(new Error(message.error.message)); else item.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') {
      const detail = message.params.exceptionDetails;
      summary.browser_errors.push(detail.exception?.description || detail.text);
    } else if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
      summary.browser_errors.push(message.params.args.map(item => item.description || item.value || '').join(' '));
    }
  });
  socket.addEventListener('close', () => {
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('검사용 CDP 연결이 닫혔습니다.')); }
    pending.clear();
  });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chrome 연결 시간 초과')), 5000);
    socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Chrome 연결 실패')); }, { once: true });
  });
  await command('Page.enable');
  await command('Runtime.enable');
  summary.browser_version = await command('Browser.getVersion');
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `(${installFixture.toString()})();` });
  await loadViewport(1600, 1500, false);
  await check('검사 자료만 표시: 입력 7개, 공동 1위 두 명·단독 두 명·본인 도전 중', async () => {
    const counts = await evaluate('({ guesses: document.querySelectorAll(".guess-table tbody tr").length, ranking: document.querySelectorAll(".ranking-table tbody tr").length, joint: document.querySelectorAll(".joint-rank").length, me: document.querySelectorAll(".my-ranking-row .me-label").length })');
    assert.deepEqual(counts, { guesses: 7, ranking: 5, joint: 2, me: 1 });
    assert.equal(await evaluate('document.querySelectorAll(".message.notice, .header-note, .game-guide, #guess-help, .ranking-note, .site-footer").length'), 0);
    assert.equal(await evaluate('document.querySelector("#guess").getAttribute("aria-describedby")'), null);
    return counts;
  });
  await check('서버 한국 날짜 표시·어제 정답 있음/없음·오늘 정답 숨김', async () => {
    assert.equal(await evaluate('document.querySelector(".puzzle-date").dateTime'), '2031-12-31');
    assert.equal(await evaluate('document.querySelector(".puzzle-date").textContent'), '2031년 12월 31일');
    assert.equal(await evaluate('document.querySelector(".yesterday-answer").textContent'), '어제의 정답: 겨울');
    assert(!await evaluate('document.body.textContent.includes("매일 00:00 변경") || document.body.textContent.includes(window.__GANMANTLE_UI_TEST__.today_answer)'));
    await evaluate('window.__GANMANTLE_UI_TEST__.state.yesterday_answer = null; window.dispatchEvent(new Event("focus"));');
    await until('!document.querySelector(".yesterday-answer")', '어제 문제 없는 안내 숨김');
    assert.equal(await evaluate('document.querySelector(".puzzle-date").textContent'), '2031년 12월 31일');
    await evaluate('window.__GANMANTLE_UI_TEST__.state.yesterday_answer = "겨울"; window.dispatchEvent(new Event("focus"));');
    await until('document.querySelector(".yesterday-answer")?.textContent === "어제의 정답: 겨울"', '어제 정답 복원');
  });
  await check('최근 입력 한 행 분리·나머지 점수 내림차순·원점수 동률은 최초 시도순', async () => {
    const rows = await assertGuessOrder('산책', ['책', '바람', '하늘', '여행', '바다', '나무'], 7);
    assert.deepEqual(rows.slice(1, 4).map(row => [row.score, row.attempt]), [['45.68', 2], ['45.68', 3], ['45.68', 4]]);
    assert.deepEqual(await evaluate('window.__GANMANTLE_UI_TEST__.state.game.guesses.map(item => item.word)'), ['산책', '여행', '바다', '하늘', '바람', '책', '나무']);
    const border = await evaluate('getComputedStyle(document.querySelector(".latest-guess td")).borderBottomWidth');
    assert(parseFloat(border) >= 2, '최근 행 아래 구분선이 없습니다.');
    return rows;
  });
  await check('공동 순위에만 풀이 시간 표시: 같은 횟수의 다른 순위·단독·진행 중은 숨김', async () => {
    const rows = await evaluate(`[...document.querySelectorAll('.ranking-table tbody tr')].map(row => ({
      joint: !!row.querySelector('.joint-rank'), time: row.querySelector('.ranking-player-time')?.textContent || null
    }))`);
    assert.equal(rows.length, 5);
    assert.deepEqual(rows.map(row => row.joint), [true, true, false, false, false]);
    assert.deepEqual(rows.map(row => row.time !== null), [true, true, false, false, false]);
    assert(rows[0].time.includes('1분 33초'));
    assert(!await evaluate('!!document.querySelector(".game-summary .timer") || /\\d+분\\s*\\d+초/.test(document.querySelector(".game-card").textContent)'));
    return rows;
  });
  await check('기준 유사도 1·10·1,000위는 응답 점수를 소수 둘째 자리로 표시', async () => {
    const values = await evaluate('[...document.querySelectorAll(".similarity-reference [data-reference-rank]")].map(el => ({ rank: el.dataset.referenceRank, score: el.textContent }))');
    assert.deepEqual(values, [{ rank: '1', score: '88.12' }, { rank: '10', score: '79.57' }, { rank: '1000', score: '24.50' }]);
    assert(!await evaluate('!!document.querySelector(".reference-status")'));
    return values;
  });
  await check('데스크톱 기준 유사도: 제목 왼쪽·세 그룹 동일 너비·한 줄 배치', () => referenceLayout(false));
  await check('단어 순위 경계 1·1,000·범위 밖: 단일색 막대의 길이는 순위 기준', async () => {
    const rows = await evaluate(`[...document.querySelectorAll('.guess-table tbody tr')].map(row => {
      const rank = row.querySelector('[data-similarity-rank]');
      const track = row.querySelector('.rank-track');
      const fill = row.querySelector('.rank-fill');
      return { word: row.querySelector('.guess-word').firstChild.textContent, rank: rank.dataset.similarityRank, label: row.querySelector('.word-rank').textContent,
        score: row.querySelector('.score').textContent, percent: parseFloat(fill.style.width),
        width: fill.getBoundingClientRect().width, trackWidth: track.getBoundingClientRect().width, color: getComputedStyle(fill).backgroundColor };
    })`);
    assert.deepEqual(rows.map(row => row.rank), ['1', '500', '750', '250', '1000', 'outside', 'outside']);
    const byWord = Object.fromEntries(rows.map(row => [row.word, row]));
    assert.equal(byWord.산책.label, '1위');
    assert.equal(byWord.산책.percent, 100);
    assert(Math.abs(byWord.산책.width - byWord.산책.trackWidth) <= 1);
    assert.equal(byWord.여행.label, '1,000위');
    assert(Math.abs(byWord.여행.percent - 0.1) < 0.00001 && byWord.여행.width >= 3);
    assert.equal(byWord.바다.label, '1,000위 밖');
    assert.equal(byWord.바다.percent, 0); assert.equal(byWord.바다.width, 0);
    assert.equal(byWord.하늘.score, byWord.바람.score); // 같은 표시 점수여도 서버 순위가 다르면 막대 길이가 다릅니다.
    assert(Math.abs(byWord.하늘.percent - 75.1) < 0.00001 && Math.abs(byWord.바람.percent - 25.1) < 0.00001);
    assert.equal(new Set(rows.map(row => row.color)).size, 1, '막대 채움 색은 순위에 관계없이 같아야 합니다.');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".ranking-similarity-rank")].map(el => el.textContent)'), ['정답', '정답', '정답', '정답', '1위']);
    return rows;
  });
  await check('순위 기준 오류는 정답 0위도 숨김·실제 안내·복구 후 원래 점수 및 순위', async () => {
    const healthy = await evaluate('window.__GANMANTLE_UI_TEST__.state.similarity_reference');
    const firstRank = await evaluate('window.__GANMANTLE_UI_TEST__.state.game.guesses[0].similarity_rank');
    await evaluate(`(() => {
      Object.assign(window.__GANMANTLE_UI_TEST__.state.similarity_reference, { ready: false, error: 'TEST ONLY 순위 기준을 읽지 못했어요.' });
      window.__GANMANTLE_UI_TEST__.state.game.guesses[0].similarity_rank = 0;
      window.dispatchEvent(new Event('focus'));
    })()`);
    await until('document.querySelector(".reference-status")?.textContent === "TEST ONLY 순위 기준을 읽지 못했어요."', '순위 준비 오류');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".similarity-reference strong")].map(el => el.textContent)'), ['—', '—', '—']);
    assert(await evaluate('[...document.querySelectorAll("[data-similarity-rank]")].every(el => el.dataset.similarityRank === "unavailable")'));
    assert(await evaluate('[...document.querySelectorAll(".word-rank, .word-rank-label")].every(el => el.textContent === "—")'));
    assert(await evaluate('[...document.querySelectorAll(".guess-table .rank-fill")].every(el => parseFloat(el.style.width) === 0)'));
    assert.equal(await evaluate('document.querySelector(".guess-table .rank-fill").getBoundingClientRect().width'), 0);
    await evaluate(`window.__GANMANTLE_UI_TEST__.state.similarity_reference = ${JSON.stringify(healthy)}; window.__GANMANTLE_UI_TEST__.state.game.guesses[0].similarity_rank = ${JSON.stringify(firstRank)}; window.dispatchEvent(new Event('focus'));`);
    await until('!document.querySelector(".reference-status") && document.querySelector(".guess-table [data-similarity-rank]")?.dataset.similarityRank === "1"', '순위 기준 복구');
  });
  await check('모델 점수 갱신 안내 숨김: 갱신 시각·null·필드 없음 모두 숨김·입력 기록 유지', async () => {
    assert.equal(await evaluate('document.querySelectorAll(".model-update-notice").length'), 0);
    const gameSnapshot = '({ table: document.querySelector(".guess-table").textContent, input: document.querySelector("#guess").value, attempts: document.querySelector(".game-summary strong").textContent })';
    const before = await evaluate(gameSnapshot);
    for (const [label, update] of [
      ['갱신 시각 있는 응답', 'model.scores_updated_at = new Date().toISOString()'],
      ['갱신 시각 null 응답', 'model.scores_updated_at = null'],
      ['선택 메타 필드 없는 응답', 'delete model.scores_updated_at'],
    ]) {
      const requests = await evaluate('window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === "/api/state").length');
      await evaluate(`(() => {
        const model = window.__GANMANTLE_UI_TEST__.state.model;
        ${update};
        window.dispatchEvent(new Event('focus'));
      })()`);
      // 안내가 원래 없으므로, 응답 조회와 렌더를 기다린 뒤에도 없는지 확인합니다.
      await until(`window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === '/api/state').length > ${requests}`, label);
      await settleFrame();
      assert.equal(await evaluate('document.querySelectorAll(".model-update-notice").length'), 0);
      assert.deepEqual(await evaluate(gameSnapshot), before);
      if (label === '갱신 시각 있는 응답') await screenshot('ui-model-update.png');
    }
    assert.equal(before.attempts, '7');
  });
  const desktopWidth = await evaluate('document.querySelector(".game-card").getBoundingClientRect().width');
  await check('데스크톱 본문 너비 축소·양옆 여백 확대', async () => {
    const card = await evaluate('(() => { const r = document.querySelector(".game-card").getBoundingClientRect(); return { width: r.width, left: r.left, rightMargin: document.documentElement.clientWidth - r.right }; })()');
    assert(Math.abs(card.width - 640) <= 1);
    assert(card.left >= 470 && card.rightMargin >= 470);
    assert(Math.abs(card.left - card.rightMargin) <= 1);
    return card;
  });
  await screenshot('ui-layout.png');
  await openChat();
  await check('데스크톱 1600×1500: 화면·입력·채팅 경계', async () => {
    assert.equal(await evaluate('document.querySelectorAll(".chat-compose-help").length'), 0);
    assert(!await evaluate('document.querySelector(".chat-panel").textContent.includes("실시간 연결됨")'));
    return layout(false);
  });
  await screenshot('ui-desktop.png');
  await check('닫기 버튼과 채팅 토글이 게임 너비를 바꾸지 않음', async () => {
    assert.equal(await evaluate('document.querySelector(".game-card").getBoundingClientRect().width'), desktopWidth);
    await evaluate('document.querySelector(".chat-close").click()');
    await until('!document.querySelector(".chat-panel")', '닫기 버튼');
    assert.equal(await evaluate('document.querySelector(".game-card").getBoundingClientRect().width'), desktopWidth);
    await openChat();
    await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await command('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await until('!document.querySelector(".chat-panel") && document.activeElement?.classList.contains("chat-toggle")', 'Escape 닫기와 포커스');
  });
  await check('거절 단어: 입력 비움·안내·포커스 복귀·시도 유지·재연결 버튼 없음', async () => {
    await setWord('아무거나ㅏㅣㅓ');
    await until('document.querySelector("#guess").value === "" && document.querySelector(".message.warning")?.textContent.includes("입력할 수 없는 단어")', '거절 안내');
    assert(await evaluate('document.activeElement === document.querySelector("#guess")'));
    assert.equal(await evaluate('document.querySelectorAll(".guess-table tbody tr").length'), 7);
    assert(!await evaluate('[...document.querySelectorAll("button")].some(el => el.textContent === "다시 연결")'));
    const before = await evaluate('window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === "/api/state").length');
    await evaluate('window.dispatchEvent(new Event("focus"))');
    await until(`window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === '/api/state').length > ${before}`, '상태 재조회');
    assert(await evaluate('document.querySelector(".message.warning")?.textContent.includes("입력할 수 없는 단어")'));
  });
  await check('정상 단어: 새 행·시도 추가·입력과 이전 안내 비움', async () => {
    await setWord('사과');
    await until('document.querySelector("#guess").value === "" && document.querySelectorAll(".guess-table tbody tr").length === 8', '정상 제출');
    assert(await evaluate('document.querySelector(".guess-table tbody tr .guess-word").textContent.includes("사과")'));
    assert(!await evaluate('document.querySelector(".message.warning")?.textContent.includes("입력할 수 없는 단어")'));
    await assertGuessOrder('사과', ['산책', '책', '바람', '하늘', '여행', '바다', '나무'], 8);
  });
  await check('중복 입력 재표시에서도 단어 순위 유지·행과 시도 횟수 불변', async () => {
    await setWord('산책');
    await until('document.querySelector(".latest-guess .guess-word")?.firstChild.textContent === "산책" && document.querySelector("#guess").value === ""', '중복 단어의 최근 행 이동');
    const row = await evaluate('(() => { const el = document.querySelector(".guess-table tbody tr"); return { word: el.querySelector(".guess-word").textContent, rank: el.querySelector("[data-similarity-rank]").dataset.similarityRank, attempt: el.querySelector(".attempt").textContent }; })()');
    assert(row.word.includes('산책')); assert.equal(row.rank, '1'); assert.equal(row.attempt, '7');
    assert.equal(await evaluate('document.querySelectorAll(".guess-table tbody tr").length'), 8);
    assert.equal(await evaluate('document.querySelector(".game-summary strong").textContent'), '8');
    await assertGuessOrder('산책', ['사과', '책', '바람', '하늘', '여행', '바다', '나무'], 8);
    // 낮은 점수와 동률 단어를 재입력해도 이전 최근 행은 점수순 위치로 돌아갑니다.
    for (const [word, previous] of [
      ['책', ['산책', '사과', '바람', '하늘', '여행', '바다', '나무']],
      ['여행', ['산책', '사과', '책', '바람', '하늘', '바다', '나무']],
      ['산책', ['사과', '책', '바람', '하늘', '여행', '바다', '나무']],
    ]) {
      await setWord(word);
      await until(`document.querySelector('.latest-guess .guess-word')?.firstChild.textContent === ${JSON.stringify(word)} && document.querySelector('#guess').value === ''`, '중복 단어의 최근 행 이동');
      assert.equal(await evaluate('document.querySelectorAll(".message.notice").length'), 0);
      await assertGuessOrder(word, previous, 8);
    }
  });
  summary.desktop_api_requests = await evaluate('window.__GANMANTLE_UI_TEST__.requests');
  await check('정답 완료 화면에서도 시간 숨김·시도 횟수 유지', async () => {
    await evaluate(`(() => {
      const state = window.__GANMANTLE_UI_TEST__.state;
      state.game.status = 'completed';
      state.game.completed_at = new Date().toISOString();
      state.game.elapsed_ms = 754000;
      state.game.guesses[0].is_correct = true;
      state.game.guesses[0].similarity_rank = 0;
      state.game.guesses[0].similarity = 100;
      window.dispatchEvent(new Event('focus'));
    })()`);
    await until('!!document.querySelector(".success-panel")', '완료 화면');
    assert.equal(await evaluate('document.querySelector(".game-summary strong").textContent'), '8');
    assert(await evaluate('document.querySelector(".success-panel").textContent.includes("정답이에요!") && document.querySelector(".success-panel").textContent.includes("산책")'));
    assert(!await evaluate('document.querySelector(".success-panel").textContent.includes("내일 또 만나요")'));
    assert(!await evaluate('!!document.querySelector(".game-summary .timer") || /\\d+분\\s*\\d+초/.test(document.querySelector(".game-card").textContent)'));
    assert.equal(await evaluate('document.querySelector(".guess-table .correct-row [data-similarity-rank]").dataset.similarityRank'), '0');
    assert.equal(await evaluate('document.querySelector(".guess-table .correct-row .word-rank").textContent'), '정답');
    assert.equal(await evaluate('document.querySelector(".guess-table .correct-row .rank-fill").style.width'), '100%');
  });
  await check('자정 자동 재조회·중복 응답의 새 날짜와 어제 정답 전환·배너 및 오늘 정답 숨김', async () => {
    const before = await evaluate('window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === "/api/state").length');
    assert(!await evaluate('document.body.textContent.includes(window.__GANMANTLE_UI_TEST__.today_answer)'));
    await evaluate(`(() => {
      const fixture = window.__GANMANTLE_UI_TEST__;
      fixture.state.server_now = '2031-12-31T14:59:59.800Z';
      fixture.state.next_reset_at = '2031-12-31T15:00:00.000Z';
      fixture.rolloverAfterNextStateRead = {
        server_now: '2031-12-31T15:00:00.050Z', puzzle_date: '2032-01-01',
        yesterday_answer: fixture.today_answer, next_reset_at: '2032-01-01T15:00:00.000Z',
        game: null, ranking: { completed: [], playing: [] },
      };
      fixture.today_answer = '노을';
      window.dispatchEvent(new Event('focus'));
    })()`);
    await until('document.querySelector(".puzzle-date")?.textContent === "2032년 1월 1일" && document.querySelector(".yesterday-answer")?.textContent === "어제의 정답: 달빛"', '한국 시간 자정 날짜·정답 전환');
    assert.equal(await evaluate('document.querySelector(".puzzle-date").dateTime'), '2032-01-01');
    assert(await evaluate(`window.__GANMANTLE_UI_TEST__.requests.filter(item => item.path === '/api/state').length >= ${before + 2}`));
    assert.equal(await evaluate('document.querySelectorAll(".message.notice").length'), 0);
    assert(await evaluate('!!document.querySelector(".start-button") && !document.querySelector(".guess-table")'));
    assert(!await evaluate('document.body.textContent.includes(window.__GANMANTLE_UI_TEST__.today_answer)'));
    // 자정 직전 중복 제출이 성공한 뒤 새 날짜 상태를 받는 경우도 같은 검사에서 확인합니다.
    await evaluate(`(() => {
      const fixture = window.__GANMANTLE_UI_TEST__;
      fixture.state.server_now = '2032-01-01T14:00:00.000Z';
      fixture.state.game = {
        status: 'playing', started_at: '2032-01-01T13:59:59.000Z', completed_at: null, elapsed_ms: 1000, attempts: 1,
        guesses: [{ word: '산책', similarity: 88.1234, similarity_rank: 1, attempt: 1, is_correct: false }],
      };
      fixture.rolloverAfterNextGuess = {
        server_now: '2032-01-01T15:00:00.050Z', puzzle_date: '2032-01-02', yesterday_answer: fixture.today_answer,
        next_reset_at: '2032-01-02T15:00:00.000Z', game: null, ranking: { completed: [], playing: [] },
      };
      fixture.today_answer = '밤하늘';
      window.dispatchEvent(new Event('focus'));
    })()`);
    await until('!!document.querySelector("#guess:not(:disabled)")', '자정 직전 중복 제출 준비');
    await setWord('산책');
    await until('document.querySelector(".puzzle-date")?.dateTime === "2032-01-02" && !!document.querySelector(".start-button")', '중복 응답의 새 날짜 적용');
    assert.equal(await evaluate('document.querySelectorAll(".message.notice").length'), 0);
    assert.equal(await evaluate('document.querySelector(".yesterday-answer").textContent'), '어제의 정답: 노을');
    assert(!await evaluate('document.body.textContent.includes("날짜가 바뀌어") || document.body.textContent.includes("이미 입력한 단어") || document.body.textContent.includes(window.__GANMANTLE_UI_TEST__.today_answer)'));
    assert.equal(await evaluate('document.querySelectorAll(".start-panel p").length'), 0);
    assert(!await evaluate('document.querySelector(".game-card").textContent.includes("시작 버튼을 눌러")'));
    // 동일한 새 날짜에서 닉네임 진입과 게임 준비 상태도 확인합니다. API 요청은 계속 검사 자료만 사용합니다.
    await evaluate('window.__GANMANTLE_UI_TEST__.state.user = null; window.dispatchEvent(new Event("focus"));');
    await until('!!document.querySelector("#nickname") && !document.querySelector(".start-button")', '닉네임 설정 화면');
    assert.equal(await evaluate('document.querySelector("#nickname-help").textContent'), '2~20자');
    assert.equal(await evaluate('document.querySelector("#nickname").getAttribute("aria-describedby")'), 'nickname-help');
    assert(!await evaluate('document.querySelector(".game-card").textContent.includes("닉네임을 정하고") || document.querySelector(".game-card").textContent.includes("같은 브라우저")'));
    await screenshot('ui-nickname.png');
    await evaluate(`(() => {
      const state = window.__GANMANTLE_UI_TEST__.state;
      state.model.ready = false;
      state.model.error = 'TEST ONLY internal model path';
      window.dispatchEvent(new Event('focus'));
    })()`);
    await until('document.querySelector(".message.warning")?.textContent.includes("게임을 준비하고 있어요")', '게임 준비 상태 안내');
    assert(!await evaluate('document.body.textContent.includes("TEST ONLY internal model path")'));
  });
  await loadViewport(390, 844, true);
  await check('모바일 390px 기준 유사도: 세 그룹 동일 너비·제목/순위/점수 겹침과 잘림 없음', () => referenceLayout(true));
  const mobileWidth = await evaluate('document.querySelector(".game-card").getBoundingClientRect().width');
  await openChat();
  await check('모바일 390×844: 표 내부만 가로 스크롤·채팅과 입력 경계', () => layout(true));
  await screenshot('ui-mobile.png');
  await check('모바일 채팅을 열고 닫아도 게임 너비 유지', async () => {
    assert.equal(await evaluate('document.querySelector(".game-card").getBoundingClientRect().width'), mobileWidth);
    await evaluate('document.querySelector(".chat-close").click()');
    await until('!document.querySelector(".chat-panel")', '모바일 닫기');
    assert.equal(await evaluate('document.querySelector(".game-card").getBoundingClientRect().width'), mobileWidth);
  });
  await loadViewport(320, 844, true);
  await check('모바일 320px 기준 유사도: 세 그룹 동일 너비·제목/순위/점수 겹침과 잘림 없음', () => referenceLayout(true));
  await screenshot('ui-mobile-320.png');
  await check('브라우저 JavaScript 오류 없음', async () => assert.deepEqual(summary.browser_errors, []));
  summary.passed = true;
} catch (error) {
  summary.error = error.stack || error.message;
  process.exitCode = 1;
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close', {}, 2000); }
    catch (error) { summary.browser_close = error.message; }
    socket.close();
  }
  summary.profile_cleanup = { created: profileCreated, removed: false };
  try {
    // close는 상속된 stdio까지 기다리므로 실제 프로세스의 exit/종료 코드로 확인합니다.
    const hasExited = () => {
      if (!chrome || chromeExited || chrome.exitCode !== null || chrome.signalCode !== null
        || (spawnError && !chrome.pid)) return true;
      // Windows에서 종료 이벤트가 늦으면 OS에도 존재하지 않는 PID인지 확인합니다.
      try { process.kill(chrome.pid, 0); return false; }
      catch (error) { return error.code === 'ESRCH'; }
    };
    if (!hasExited()) {
      let deadline = Date.now() + 15000;
      while (!hasExited() && Date.now() < deadline) await sleep(100);
      if (!hasExited()) {
        summary.profile_cleanup.forced_stop = chrome.kill(); // 이번 검사의 자식 PID만 종료합니다.
        deadline = Date.now() + 15000;
        while (!hasExited() && Date.now() < deadline) await sleep(100);
      }
    }
    summary.profile_cleanup.process_exited = hasExited();
    summary.profile_cleanup.exit_code = chrome?.exitCode ?? null;
    summary.profile_cleanup.signal = chrome?.signalCode ?? null;
    if (spawnError) summary.profile_cleanup.process_error = spawnError.message;
    if (profileCreated) {
      assert(hasExited(), 'Chrome 종료를 확인하지 못해 검사 프로필을 남겼습니다.');
      const actualRoot = await realpath(root);
      const actualOutput = await realpath(output);
      const actualProfile = await realpath(profile);
      assert.equal(path.relative(actualRoot, actualOutput), 'test-results', '검사 결과 폴더가 프로젝트 밖을 가리킵니다.');
      assert.equal(path.relative(actualOutput, actualProfile), path.basename(profile), '현재 검사 프로필 경로가 맞지 않습니다.');
      assert(path.basename(actualProfile).startsWith('ui-profile-'), '검사 프로필 이름이 맞지 않습니다.');
      await rm(actualProfile, { recursive: true, force: false, maxRetries: 5, retryDelay: 200 });
      summary.profile_cleanup.removed = true;
    }
  } catch (error) {
    summary.passed = false;
    summary.cleanup_error = `검사 프로필 정리 실패: ${error.message}`;
    summary.error ||= summary.cleanup_error;
    process.exitCode = 1;
    console.error(summary.cleanup_error);
  } finally {
    // 정리 실패는 그대로 보고하고, 상속된 파이프로 검사 Node까지 멈추지 않게 합니다.
    chrome?.stderr?.destroy();
    chrome?.unref();
  }
  summary.finished_at = new Date().toISOString();
  await mkdir(output, { recursive: true });
  await writeFile(path.join(output, 'ui-checks.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ passed: summary.passed, checks: summary.checks.length, result: 'test-results/ui-checks.json', screenshots: summary.screenshots, profile_cleanup: summary.profile_cleanup, error: summary.error, cleanup_error: summary.cleanup_error }, null, 2));
}
