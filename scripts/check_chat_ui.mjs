// 격리된 serve_chat_check.py 서버에만 쓰는 실제 API·DB·SSE·브라우저 통합 검사.
// Node 24와 설치된 Chrome 사용. 기존 사용자 프로필·본 앱 DB를 사용하지 않습니다.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'test-results');
const profile = path.join(output, `chat-profile-${Date.now()}-${process.pid}`);
const chromePath = process.env.CHROME_PATH || (process.platform === 'win32'
  ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  : process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'google-chrome');
const base = new URL(process.env.CHAT_CHECK_URL || 'http://localhost:8001');
assert(['localhost', '127.0.0.1', '[::1]'].includes(base.hostname), '로컬 검사 서버만 허용합니다.');
const globalRoom = '00000000-0000-0000-0000-000000000001';
const runTag = Date.now().toString(36).slice(-5);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const summary = { isolated_database: true, fake_api: false, checks: [], browser_errors: [], passed: false };
let chrome, socket, exited = false, spawnError, sequence = 0;
let profileCreated = false;
const pending = new Map();
const contexts = new Map();

function command(method, params = {}, sessionId, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, timeout);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}
async function evaluate(page, expression) {
  let result;
  try { result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, page); }
  catch(error) { throw Error(`${error.message}: ${expression.slice(0,180)}`); }
  if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
}
async function until(page, expression, label, timeout = 30000) {
  await command('Page.bringToFront', {}, page);
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    try { if (await evaluate(page, expression)) return; }
    catch (error) { if (!/context|navigat/i.test(error.message)) throw error; }
    await sleep(100);
  }
  summary.failure_page=await evaluate(page,'({url:location.href,title:document.title,text:document.body?.innerText?.slice(0,1200)})');
  await screenshot(page,'chat-failure.png');
  throw Error(`화면 대기 실패: ${label}`);
}
async function reload(page, ready) {
  const previous=await evaluate(page,'window.__documentId');
  await command('Page.reload',{},page);
  await until(page,`window.__documentId && window.__documentId !== ${JSON.stringify(previous)} && document.readyState === 'complete' && (${ready})`,'새 문서 로드');
}
async function api(page, route, body) {
  return evaluate(page, `(async () => {
    const r = await fetch('/api${route}', {method:${JSON.stringify(body ? 'POST' : 'GET')},credentials:'same-origin',headers:{'Content-Type':'application/json'},${body ? `body:JSON.stringify(${JSON.stringify(body)}),` : ''}});
    return {status:r.status,body:await r.json()};
  })()`);
}
async function ok(page, route, body) { const r = await api(page, route, body); assert.equal(r.status, 200, `${route}: ${r.status}`); return r.body; }
async function fill(page, selector, value) {
  await command('Page.bringToFront',{},page);
  await evaluate(page, `(() => { const el = document.querySelector(${JSON.stringify(selector)}); if(!el)throw Error('input missing');
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});
    el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true})); })()`);
}
async function clickText(page, text, scope = 'body') {
  await command('Page.bringToFront',{},page);
  await until(page, `[...document.querySelectorAll(${JSON.stringify(`${scope} button`)})].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`, text);
  await evaluate(page, `[...document.querySelectorAll(${JSON.stringify(`${scope} button`)})].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);
}
async function check(name, action) {
  await action(); summary.checks.push(name); console.log(`통과: ${name}`);
}
async function screenshot(page, name) {
  await command('Page.bringToFront', {}, page);
  const { data } = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, page);
  await writeFile(path.join(output, name), Buffer.from(data, 'base64'));
}
async function createPage(nickname, sameSession) {
  const browserContextId = sameSession ? contexts.get(sameSession) : (await command('Target.createBrowserContext')).browserContextId;
  const { targetId } = await command('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await command('Target.attachToTarget', { targetId, flatten: true });
  contexts.set(sessionId,browserContextId);
  await command('Page.enable', {}, sessionId); await command('Runtime.enable', {}, sessionId);
  await command('Emulation.setDeviceMetricsOverride', { width: 1300, height: 1000, deviceScaleFactor: 1, mobile: false }, sessionId);
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    window.__documentId=crypto.randomUUID(); window.__chatEvents=0;
    const RealEventSource=window.EventSource;
    window.EventSource=class extends RealEventSource { constructor(...args){super(...args);this.addEventListener('refresh',()=>window.__chatEvents++);} };
    addEventListener('DOMContentLoaded',()=>{ const b=document.createElement('div');b.textContent='TEST ONLY · 격리된 DB의 실제 채팅 검사';b.style.cssText='position:fixed;top:0;left:0;right:0;z-index:9999;background:#fff2ce;text-align:center;font:11px/20px sans-serif;pointer-events:none';document.body.append(b); });
  ` }, sessionId);
  await command('Page.navigate', { url: base.href }, sessionId);
  if(sameSession){await until(sessionId,'!!document.querySelector("#guess")','같은 세션의 새 탭');return sessionId;}
  await until(sessionId, '!!document.querySelector("#nickname")', '닉네임');
  await fill(sessionId, '#nickname', nickname); await clickText(sessionId, '닉네임 설정');
  await until(sessionId, '!!document.querySelector(".start-button")', '닉네임 저장');
  return sessionId;
}
async function openChat(page) {
  if (!await evaluate(page, '!!document.querySelector(".chat-panel")')) await clickText(page, '채팅 열기');
  await until(page, '!!document.querySelector("#chat-message:not(:disabled)")', '채팅 입력');
}
async function sendUi(page, body) {
  await fill(page, '#chat-message', body); await clickText(page, '보내기', '.chat-panel');
  await until(page, 'document.querySelector("#chat-message").value === ""', '전송 완료');
}

try {
  const marker = await fetch(new URL('/api/test-context', base), { signal: AbortSignal.timeout(5000) }).then(r => r.json());
  assert.equal(marker.isolated_chat_check, true, '기존 앱에는 테스트 메시지를 쓰지 않습니다. 검사 서버를 먼저 실행하세요.');
  const initial = await fetch(new URL('/api/state', base), { signal: AbortSignal.timeout(60000) }).then(r => r.json());
  assert(initial.model?.ready && initial.similarity_reference?.ready, '검사 서버의 실제 모델과 단어 순위 준비가 필요합니다.');
  await mkdir(output, { recursive: true });
  await mkdir(profile);
  profileCreated = true;
  chrome = spawn(chromePath, [
    '--headless=new', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-sync', 'about:blank',
  ], { windowsHide: true, stdio: ['ignore', 'ignore', 'ignore'] });
  chrome.on('error', e => { spawnError = e; }); chrome.on('exit', () => { exited = true; });
  let port;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (spawnError) throw spawnError; if (exited) throw Error('검사용 Chrome 시작 실패');
    try { port = Number((await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); if (port) break; }
    catch (e) { if (!['ENOENT', 'EBUSY'].includes(e.code)) throw e; }
    await sleep(100);
  }
  assert(port, '30초 안에 Chrome 검사 포트를 찾지 못했습니다.');
  const version = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(3000) }).then(r => r.json());
  summary.browser = version.Browser;
  socket = new WebSocket(version.webSocketDebuggerUrl);
  socket.addEventListener('message', e => {
    const m = JSON.parse(e.data);
    if (m.id) { const p = pending.get(m.id); if (!p) return; clearTimeout(p.timer); pending.delete(m.id); m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result); }
    else if (m.method === 'Runtime.exceptionThrown') summary.browser_errors.push(m.params.exceptionDetails.text);
  });
  socket.addEventListener('close', () => { for (const p of pending.values()) { clearTimeout(p.timer); p.reject(Error('CDP closed')); } pending.clear(); });
  await new Promise((resolve, reject) => { const t=setTimeout(()=>reject(Error('Chrome 연결 시간 초과')),5000);socket.addEventListener('open',()=>{clearTimeout(t);resolve();},{once:true});socket.addEventListener('error',()=>{clearTimeout(t);reject(Error('Chrome 연결 실패'));},{once:true}); });
  const first = await createPage(`검사하나${runTag}`);
  const second = await createPage(`검사둘${runTag}`);
  const third = await createPage(`검사셋${runTag}`);
  let before, secondUser, privateRoom, group;
  await check('서로 다른 세 브라우저 세션과 실제 게임 시작', async () => {
    const a=await ok(first,'/state'), b=await ok(second,'/state'), c=await ok(third,'/state');
    assert(new Set([a.user.id,b.user.id,c.user.id]).size===3); secondUser=b.user.id;
    await ok(first,'/start',{puzzle_date:a.puzzle_date}); await ok(second,'/start',{puzzle_date:b.puzzle_date});
    before=await ok(first,'/state');
    await reload(first,'!!document.querySelector("#guess")');
  });
  await openChat(first); await openChat(second); await openChat(third);
  // 정상 연결 문구 대신 실제 SSE 이벤트 수신과 연결 중/실패 상태 해소를 기다립니다.
  for(const page of [first,second,third]) await until(page,'window.__chatEvents >= 1 && !document.querySelector(".chat-connection")','초기 SSE 연결');
  await check('전체 대화 UI 전송 → 다른 세션의 실제 SSE 수신', async () => {
    const events=await evaluate(second,'window.__chatEvents');
    const body=`전체 채팅 실제 수신 검사 ${runTag}`;
    await sendUi(first,body);
    await until(second,`document.querySelector(".chat-panel").textContent.includes(${JSON.stringify(body)})`,'상대 수신');
    assert(await evaluate(second,`window.__chatEvents > ${events}`));
  });
  await check('팝업 닫기·재열기·새로고침 후 작성 중 초안 유지', async () => {
    await fill(first,'#chat-message','아직 보내지 않은 초안');
    await clickText(first,'닫기','.chat-panel'); await openChat(first);
    assert.equal(await evaluate(first,'document.querySelector("#chat-message").value'),'아직 보내지 않은 초안');
    await reload(first,'!!document.querySelector("#guess")'); await openChat(first);
    assert.equal(await evaluate(first,'document.querySelector("#chat-message").value'),'아직 보내지 않은 초안');
  });
  await check('개인 대화 생성·제삼자 조회/전송 차단', async () => {
    await clickText(first,`검사둘${runTag}`,'.ranking-table');
    await clickText(first,'대화하기','.chat-person-action');
    await until(first,'!!document.querySelector("#chat-room") && document.querySelector("#chat-room").value !== ""','개인 대화 선택');
    const privateId=await evaluate(first,'document.querySelector("#chat-room").value');
    privateRoom=(await ok(first,'/chat/rooms')).rooms.find(r=>r.id===privateId);
    assert.equal(privateRoom.kind,'direct');
    const retry=await ok(second,'/chat/direct',{user_id:before.user.id}); assert.equal(retry.room.id,privateRoom.id);
    await sendUi(first,'개인 대화 저장 검사');
    await clickText(second,`검사하나${runTag}`,'.chat-messages');
    await clickText(second,'대화하기','.chat-person-action');
    await until(second,'document.querySelector(".chat-messages").textContent.includes("개인 대화 저장 검사")','개인 대화 수신');
    await sendUi(second,'개인 대화 답장');
    await until(first,'document.querySelector(".chat-messages").textContent.includes("개인 대화 답장")','개인 답장 수신');
    assert((await ok(second,`/chat/rooms/${privateRoom.id}/messages`)).messages.some(m=>m.body==='개인 대화 저장 검사'));
    assert.equal((await api(third,`/chat/rooms/${privateRoom.id}/messages`)).status,404);
    assert.equal((await api(third,`/chat/rooms/${privateRoom.id}/messages`,{body:'권한 없는 전송',client_id:crypto.randomUUID()})).status,404);
  });
  await check('단체방 초대·수락 전 차단·수락 후 대화 저장', async () => {
    await clickText(first,'방','.chat-tabs'); await clickText(first,'방 만들기','.chat-panel');
    await fill(first,'#chat-room-name','검사용 단체방'); await fill(first,'#chat-search',`검사둘${runTag}`);
    await until(first,`[...document.querySelectorAll('.chat-user-results button')].some(b=>b.textContent.includes('검사둘${runTag}'))`,'초대 대상 검색');
    await evaluate(first,`[...document.querySelectorAll('.chat-user-results button')].find(b=>b.textContent.includes('검사둘${runTag}')).click()`);
    await clickText(first,'방 만들고 초대','.chat-panel');
    await until(first,'!document.querySelector("#chat-room-name") && document.querySelector("#chat-room")?.value','단체방 생성');
    const groupId=await evaluate(first,'document.querySelector("#chat-room").value');
    group=(await ok(first,'/chat/rooms')).rooms.find(r=>r.id===groupId);
    assert.equal((await api(second,`/chat/rooms/${group.id}/messages`)).status,404);
    await until(second,'document.querySelector(".chat-tabs").textContent.includes("방 (1)")','실시간 초대');
    await clickText(second,'방 (1)','.chat-tabs');
    await clickText(second,'수락','.chat-panel');
    await until(second,`document.querySelector('#chat-room')?.value === ${JSON.stringify(group.id)}`,'수락한 방 선택');
    await sendUi(second,'수락한 참여자의 메시지');
    await until(first,'document.querySelector(".chat-messages").textContent.includes("수락한 참여자의 메시지")','단체방 실시간 수신');
    assert((await ok(first,`/chat/rooms/${group.id}/messages`)).messages.some(m=>m.body==='수락한 참여자의 메시지'));
    assert.equal((await api(third,`/chat/rooms/${group.id}/messages`)).status,404);
  });
  await check('닫힌 동안 받은 메시지를 다시 열 때 복원하고 HTML을 텍스트로 표시', async () => {
    await clickText(second,'닫기','.chat-panel');
    await sendUi(first,'팝업이 닫힌 동안의 메시지');
    await openChat(second);
    await until(second,'document.querySelector(".chat-messages").textContent.includes("팝업이 닫힌 동안의 메시지")','재연결 후 누락 복구');
    const html='<img src=x onerror="window.__unsafeChat=1">';
    await ok(first,`/chat/rooms/${globalRoom}/messages`,{body:html,client_id:crypto.randomUUID()});
    await until(third,`document.querySelector('.chat-messages').textContent.includes(${JSON.stringify(html)})`,'텍스트 메시지 수신');
    assert(await evaluate(third,'!window.__unsafeChat && document.querySelectorAll(".chat-messages img").length === 0'));
  });
  await check('대화 기록 재조회·메시지 재전송 멱등·게임 기록 유지', async () => {
    const payload={body:'한 번만 저장',client_id:crypto.randomUUID()};
    const a=await ok(first,`/chat/rooms/${globalRoom}/messages`,payload), b=await ok(first,`/chat/rooms/${globalRoom}/messages`,payload);
    assert.equal(a.message.id,b.message.id);
    const after=await ok(first,'/state');
    assert.equal(after.game.started_at,before.game.started_at); assert.equal(after.game.attempts,before.game.attempts);
    assert.deepEqual(after.game.guesses,before.game.guesses); assert.equal(after.puzzle_date,before.puzzle_date);
    assert.deepEqual(after.ranking,before.ranking);
    await reload(second,'!!document.querySelector("#guess")'); await openChat(second);
    assert((await ok(second,`/chat/rooms/${group.id}/messages`)).messages.some(m=>m.body==='수락한 참여자의 메시지'));
  });
  await check('같은 사용자의 다른 탭이 초안을 덮어쓰지 않음', async () => {
    await fill(first,'#chat-message','원래 탭의 초안');
    const sibling=await createPage(null,first);await openChat(sibling);
    await fill(sibling,'#chat-message','다른 탭의 초안');
    assert.equal((await ok(sibling,'/state')).user.id,before.user.id);
    await reload(first,'!!document.querySelector("#guess")');await openChat(first);
    assert.equal(await evaluate(first,'document.querySelector("#chat-message").value'),'원래 탭의 초안');
    assert.equal(await evaluate(sibling,'document.querySelector("#chat-message").value'),'다른 탭의 초안');
    await clickText(sibling,'닫기','.chat-panel');
  });
  await screenshot(first,'chat-desktop.png');
  await check('모바일 채팅 입력·닫기 경계와 페이지 가로 넘침 없음', async () => {
    await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,screenWidth:390,screenHeight:844,deviceScaleFactor:1,mobile:true},third);
    await reload(third,'!!document.querySelector(".start-button")'); await openChat(third);
    const size=await evaluate(third,`(() => {const b=s=>{const r=document.querySelector(s).getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};};return {width:innerWidth,doc:document.documentElement.scrollWidth,close:b('.chat-close'),input:b('#chat-message')};})()`);
    assert.equal(size.width,390);assert(size.doc<=390);
    for(const b of [size.close,size.input])assert(b.left>=0&&b.right<=390&&b.top>=0&&b.bottom<=844);
    await screenshot(third,'chat-mobile.png');
  });
  assert.deepEqual(summary.browser_errors,[]); summary.passed=true;
} catch(e) { summary.error=e.stack; process.exitCode=1; }
finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close',{},undefined,2000);}catch(error){summary.browser_close=error.message;}socket.close();}
  summary.profile_cleanup = { created: profileCreated, removed: false };
  try {
    // close는 상속된 stdio까지 기다리므로 실제 프로세스의 exit/종료 코드로 확인합니다.
    const hasExited = () => {
      if (!chrome || exited || chrome.exitCode !== null || chrome.signalCode !== null
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
      assert(path.basename(actualProfile).startsWith('chat-profile-'), '검사 프로필 이름이 맞지 않습니다.');
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
  await mkdir(output,{recursive:true});await writeFile(path.join(output,'chat-ui-checks.json'),JSON.stringify(summary,null,2)+'\n');
  console.log(JSON.stringify(summary,null,2));
}
