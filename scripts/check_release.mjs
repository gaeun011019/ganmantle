// 실행: node scripts/check_release.mjs (Node 24+, Docker Compose, 실행 중인 app 필요)
// 현재 앱은 읽기만 합니다. 임시 DB에서 실제 모델/API의 재시작과 논리 복원을 검사합니다.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'test-results');
const runId = `${Date.now().toString(36)}-${randomBytes(4).toString('hex')}`;
const project = `ganmantle-check-${runId}`;
const envFile = path.join(output, `${project}.env`);
const overrideFile = path.join(output, `${project}.json`);
const password = randomBytes(32).toString('hex');
const cancellation = new AbortController();
const summary = { passed: false, started_at: new Date().toISOString(), project, checks: [], cleanup: {} };
const files = [];
let stage = '준비', child, interrupted = false, cleaning = false, started = false;
let image, modelVolume, database = 'ganmantle', baseUrl, cookie = '';

class CheckFailure extends Error {}
function check(condition, message) { if (!condition) throw new CheckFailure(message); }
function progress(label) { stage = label; console.log(label); }
function passed(label) { summary.checks.push(label); }
function stop() { interrupted = true; cancellation.abort(); child?.kill(); }
process.once('SIGINT', stop);
process.once('SIGTERM', stop);

// 명령 실패 시 stderr에는 연결 문자열 등이 포함될 수 있어 그대로 출력하지 않습니다.
function docker(args, env = {}, timeout = 600_000) {
  if (interrupted && !cleaning) throw new CheckFailure('검사가 중단되었습니다.');
  return new Promise((resolve, reject) => {
    child = execFile('docker', args, { cwd: root, windowsHide: true, timeout,
      maxBuffer: 4 * 1024 * 1024, env: { ...process.env, ...env } }, (error, stdout) => {
      child = undefined;
      if (error) reject(new CheckFailure(`${stage}: Docker 명령 실패 (${typeof error.code === 'number' ? error.code : '실행/시간 제한'}).`));
      else resolve(stdout.trim());
    });
  });
}

function compose(...args) {
  return docker(['compose', '--project-directory', root, '--env-file', envFile,
    '--project-name', project, '-f', 'compose.yaml', '-f', overrideFile, ...args], {
    POSTGRES_DB: database, POSTGRES_USER: 'ganmantle', POSTGRES_PASSWORD: password,
    APP_IMAGE: image, APP_PORT: '0', APP_ORIGIN: '', COOKIE_SECURE: 'false',
  });
}

async function checkIsolation() {
  // 비밀번호가 포함된 resolved 설정은 메모리에서만 검사하고 출력하지 않습니다.
  const config = JSON.parse(await compose('config', '--format', 'json'));
  check(config.name === project && Object.keys(config.services).sort().join(',') === 'app,db', '검사 Compose 프로젝트 또는 서비스 범위가 바뀌었습니다.');
  check(Object.keys(config.volumes).sort().join(',') === 'model_data,postgres_data' &&
    config.volumes.postgres_data.name === `${project}_postgres_data` && !config.volumes.postgres_data.external &&
    config.volumes.model_data.name === modelVolume && config.volumes.model_data.external === true,
  'DB 격리 또는 공유 모델 보존 설정이 올바르지 않습니다.');
  const { app, db } = config.services;
  check(db.volumes.length === 1 && db.volumes[0].source === 'postgres_data' &&
    app.volumes.length === 1 && app.volumes[0].source === 'model_data' && app.volumes[0].read_only === true,
  '검사 앱·DB의 볼륨 연결이 예상과 다릅니다.');
  check(app.environment.DATABASE_URL === `postgresql://ganmantle:${password}@db:5432/${database}` &&
    app.ports.length === 1 && app.ports[0].host_ip === '127.0.0.1' && Number(app.ports[0].published) === 0,
  '검사 DB 연결 또는 localhost 임시 포트 설정이 올바르지 않습니다.');
}

async function waitReady() {
  const port = await compose('port', 'app', '8000');
  check(/^127\.0\.0\.1:\d+$/.test(port), '검사 앱이 localhost 임시 포트에 연결되지 않았습니다.');
  baseUrl = `http://${port}`;
  const deadline = Date.now() + 600_000;
  while (Date.now() < deadline) {
    if (interrupted) throw new CheckFailure('검사가 중단되었습니다.');
    try {
      const response = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.any([cancellation.signal, AbortSignal.timeout(5_000)]) });
      const health = await response.json();
      if (response.ok && health.status === 'ok' && health.database && health.model?.ready) return;
    } catch { /* 모델 로딩 중에는 서버 연결을 재시도합니다. */ }
    await new Promise(resolve => setTimeout(resolve, 2_000));
  }
  throw new CheckFailure('10분 내에 검사 앱의 DB·모델 준비가 완료되지 않았습니다.');
}

async function api(endpoint, body) {
  if (interrupted) throw new CheckFailure('검사가 중단되었습니다.');
  const response = await fetch(`${baseUrl}/api${endpoint}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', Origin: baseUrl, ...(cookie ? { Cookie: cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.any([cancellation.signal, AbortSignal.timeout(120_000)]),
  });
  check(response.ok, `${stage}: API 요청 실패 (HTTP ${response.status}).`);
  const issued = response.headers.getSetCookie().find(value => value.startsWith('ganmantle_session='));
  if (issued) cookie = issued.split(';', 1)[0];
  return response.json();
}

function storedState(state) {
  check(state.game, '저장한 게임을 찾을 수 없습니다.');
  const { elapsed_ms, ...game } = state.game;
  return { user: state.user, puzzle_date: state.puzzle_date, game,
    similarity_reference: state.similarity_reference, model: state.model.name };
}

async function sql(query, target = database) {
  return compose('exec', '-T', 'db', 'psql', '-U', 'ganmantle', '-d', target,
    '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1', '-c', query);
}

// 모든 일반 테이블과 sequence를 비교하되, 내용과 해시는 결과 파일에 남기지 않습니다.
async function databaseSnapshot(target) {
  const tables = (await sql("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename", target)).split(/\r?\n/);
  const rows = {};
  for (const table of tables) {
    check(/^[a-z_]+$/.test(table), '비교할 테이블 이름이 올바르지 않습니다.');
    rows[table] = await sql(`SELECT count(*) || ':' || md5(coalesce(string_agg(row_to_json(t)::text, '' ORDER BY row_to_json(t)::text), '')) FROM "${table}" t`, target);
  }
  const sequences = await sql("SELECT sequencename || ':' || coalesce(last_value::text, 'null') FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename", target);
  return { rows, sequences };
}

try {
  check(Number(process.versions.node.split('.')[0]) >= 24, 'Node 24 이상이 필요합니다.');
  progress('현재 이미지·모델 확인');
  const current = ['compose', '--project-directory', root, '--project-name', 'ganmantle-v1', '-f', 'compose.yaml'];
  image = await docker([...current, 'images', '-q', 'app']);
  check(/^(sha256:)?[a-f0-9]{12,64}$/.test(image), '실행 중인 app 이미지 하나가 필요합니다. 먼저 docker compose up -d --build를 실행하세요.');
  image = await docker(['image', 'inspect', image, '--format', '{{.Id}}']);
  const appId = await docker([...current, 'ps', '-q', 'app']);
  check(/^[a-f0-9]{12,64}$/.test(appId), '실행 중인 app 컨테이너 하나가 필요합니다.');
  const mounts = JSON.parse(await docker(['inspect', appId, '--format', '{{json .Mounts}}']));
  const model = mounts.find(mount => mount.Destination === '/models');
  check(model?.Type === 'volume' && model.RW === false, '현재 app에 읽기 전용 /models named volume이 필요합니다.');
  modelVolume = model.Name;
  check(await docker(['ps', '-aq', '--filter', `label=com.docker.compose.project=${project}`]) === '', '같은 이름의 검사 컨테이너가 이미 있습니다.');
  check(await docker(['volume', 'ls', '-q', '--filter', `label=com.docker.compose.project=${project}`]) === '', '같은 이름의 검사 볼륨이 이미 있습니다.');
  check(await docker(['volume', 'ls', '-q', '--filter', `name=${project}_postgres_data`]) === '', '검사 DB 볼륨 이름이 이미 사용 중입니다.');

  await mkdir(output, { recursive: true });
  check(path.relative(await realpath(root), await realpath(output)) === 'test-results', '검사 결과 폴더가 프로젝트 밖을 가리킵니다.');
  const example = await readFile(path.join(root, '.env.example'), 'utf8');
  await writeFile(envFile, `${example}\nPOSTGRES_PASSWORD=${password}\nAPP_PORT=0\n`, { flag: 'wx', mode: 0o600 });
  files.push(envFile);
  // external 모델은 down -v로 제거하지 않습니다. DB는 이번 검사 전용 이름으로 고정합니다.
  await writeFile(overrideFile, JSON.stringify({ services: {
    app: { image, restart: 'no' }, db: { restart: 'no' },
  }, volumes: { model_data: { external: true, name: modelVolume },
    postgres_data: { name: `${project}_postgres_data` } } }, null, 2), { flag: 'wx', mode: 0o600 });
  files.push(overrideFile);

  progress('분리된 검사 DB·앱 시작');
  await checkIsolation();
  started = true; // up 일부만 성공하더라도 finally에서 정리합니다.
  await compose('up', '-d', '--no-build', '--pull', 'never');
  await waitReady();
  passed('현재 이미지·읽기 전용 모델을 사용하는 독립 DB와 localhost 임시 포트');

  progress('실제 모델 API·중복 입력·채팅 저장');
  let state = await api('/state');
  check(state.model.ready && state.model.supports_oov && /fasttext/i.test(state.model.name), '실제 fastText 모델이 준비되지 않았습니다.');
  check(Date.parse(state.next_reset_at) - Date.parse(state.server_now) > 20 * 60_000,
    '한국 시간 자정까지 20분 이상 남았을 때 다시 검사하세요. 자정 검증은 별도 규칙 테스트를 사용합니다.');
  check(state.similarity_reference.ready, '실제 단어 순위 기준이 준비되지 않았습니다.');
  state = await api('/users', { nickname: `검사${randomBytes(4).toString('hex')}` });
  check(cookie && state.user, '닉네임과 재접속 쿠키를 만들지 못했습니다.');
  const day = state.puzzle_date;
  check(/^\d{4}-\d{2}-\d{2}$/.test(day), '서버 날짜 형식이 올바르지 않습니다.');
  state = await api('/start', { puzzle_date: day });
  const startedAt = state.game.started_at;
  // 새 검사 DB의 정답만 읽어 우연한 조기 정답을 피합니다. 실제 사용자 DB에는 접근하지 않습니다.
  const answer = await sql(`SELECT answer FROM puzzles WHERE puzzle_date = '${day}'`);
  const word = answer === '산책' ? '여행' : '산책';
  state = await api('/guesses', { puzzle_date: day, word });
  check(state.game.status === 'playing' && state.game.attempts === 1 && state.game.guesses.length === 1, '첫 입력이 정상 저장되지 않았습니다.');
  const guess = state.game.guesses[0];
  check(Number.isFinite(guess.similarity) && guess.similarity >= -100 && guess.similarity <= 100, '실제 코사인 유사도 값이 유효하지 않습니다.');
  assert.equal(state.ranking.playing[0].best_similarity, guess.similarity);
  assert.equal(state.ranking.playing[0].best_similarity_rank, guess.similarity_rank);
  state = await api('/guesses', { puzzle_date: day, word });
  check(state.duplicate && state.game.attempts === 1 && state.game.guesses.length === 1, '중복 입력으로 시도 횟수 또는 기록이 증가했습니다.');
  assert.equal(state.game.started_at, startedAt);
  passed('실제 fastText 점수·사용자 랭킹 일치와 중복 입력·시작 시각 유지');
  const rooms = await api('/chat/rooms');
  const roomId = rooms.rooms.find(room => room.kind === 'global')?.id;
  check(roomId, '전체 채팅방이 없습니다.');
  const messageBody = { body: '검사 전용 재시작 및 복원 확인', client_id: randomUUID() };
  const sent = await api(`/chat/rooms/${roomId}/messages`, messageBody);
  const messages = await api(`/chat/rooms/${roomId}/messages`);
  assert.equal(messages.messages[0].id, sent.message.id);
  passed('실제 채팅 API 메시지 저장');
  const saved = storedState(state);
  const elapsedBefore = state.game.elapsed_ms;

  progress('앱 재시작 후 같은 쿠키로 복구');
  await compose('restart', 'app');
  await waitReady();
  state = await api('/state');
  assert.deepEqual(storedState(state), saved);
  check(state.game.elapsed_ms > elapsedBefore, '재시작 후 풀이 시간이 이어지지 않았습니다.');
  assert.deepEqual(await api(`/chat/rooms/${roomId}/messages`), messages);
  state = await api('/start', { puzzle_date: day });
  assert.equal(state.game.started_at, startedAt);
  passed('재시작 후 닉네임·게임·점수·순위·채팅 복구와 풀이 시간 지속');

  progress('논리 백업·새 DB 복원');
  await compose('stop', 'app');
  const beforeRestore = await databaseSnapshot(database);
  const backup = '/tmp/ganmantle-release-check.dump';
  await compose('exec', '-T', 'db', 'pg_dump', '-U', 'ganmantle', '-d', database, '--format=custom', `--file=${backup}`);
  const restored = 'ganmantle_restore_check';
  await compose('exec', '-T', 'db', 'createdb', '-U', 'ganmantle', restored);
  await compose('exec', '-T', 'db', 'pg_restore', '-U', 'ganmantle', '--exit-on-error', '--no-owner', '--no-acl', '-d', restored, backup);
  assert.deepEqual(await databaseSnapshot(restored), beforeRestore);
  passed('pg_dump custom → 새 DB pg_restore: 모든 테이블·변경 이력·sequence 일치');

  progress('복원 DB로 앱 실행·재접속 확인');
  database = restored;
  await compose('up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', 'app');
  await waitReady();
  state = await api('/state');
  assert.deepEqual(storedState(state), saved);
  check(state.game.elapsed_ms > elapsedBefore, '복원 후 풀이 시간이 이어지지 않았습니다.');
  assert.deepEqual(await api(`/chat/rooms/${roomId}/messages`), messages);
  const resend = await api(`/chat/rooms/${roomId}/messages`, messageBody);
  assert.equal(resend.message.id, sent.message.id);
  state = await api('/guesses', { puzzle_date: day, word });
  check(state.duplicate && state.game.attempts === 1, '복원 후 중복 입력이 새 시도로 저장되었습니다.');
  assert.deepEqual(storedState(state), saved);
  passed('복원 DB에서 같은 쿠키 재접속·게임/채팅 조회·중복 요청 처리');

  progress('정답 완료 통계·상위 유사어와 실제 입력 점수 비교');
  const relatedPath = `/related-words?puzzle_date=${day}`;
  const locked = await fetch(`${baseUrl}/api${relatedPath}`, { headers: { Cookie: cookie } });
  check(locked.status === 403, '정답을 맞히기 전에 유사어 목록이 공개됐습니다.');
  assert.equal(state.player_stats, null);
  state = await api('/guesses', { puzzle_date: day, word: answer });
  check(state.game.status === 'completed' && state.game.attempts === 2, '실제 정답 완료가 저장되지 않았습니다.');
  const stats = { first_played_date: day, games_played: 1, games_completed: 1,
    current_streak: 1, games_incomplete: 0, total_guesses: 2 };
  assert.deepEqual(state.player_stats, stats);
  const related = await api(relatedPath);
  assert.equal(related.puzzle_date, day);
  assert.equal(related.words.length, 1000);
  assert.equal(new Set(related.words.map(item => item.word)).size, 1000);
  check(related.words.every(item => item.word !== answer), '유사어 목록에 정답이 포함됐습니다.');
  for (const [index, item] of related.words.entries()) {
    check(Number.isFinite(item.similarity) && item.similarity >= -100 && item.similarity <= 100,
      '유사어 목록의 점수가 유효하지 않습니다.');
    const previous = related.words[index - 1];
    if (previous) check(previous.similarity >= item.similarity, '유사어 목록이 점수순이 아닙니다.');
    assert.equal(item.rank, previous?.similarity === item.similarity ? previous.rank : index + 1);
  }
  for (const [position, key] of [[0, 'top1'], [9, 'top10'], [999, 'top1000']]) {
    assert.equal(related.words[position].similarity, state.similarity_reference[key]);
  }
  state = await api('/guesses', { puzzle_date: day, word: answer });
  check(state.duplicate && state.game.attempts === 2, '완료 후 중복 제출로 시도 수가 증가했습니다.');
  assert.deepEqual(state.player_stats, stats);
  assert.deepEqual((await api('/state')).player_stats, stats);

  // 같은 검사 DB의 다른 플레이어가 실제 입력한 점수와 목록·순위를 비교합니다.
  const completedCookie = cookie;
  cookie = '';
  await api('/users', { nickname: `비교${randomBytes(4).toString('hex')}` });
  await api('/start', { puzzle_date: day });
  for (const position of [0, 9, 999]) {
    const item = related.words[position];
    const comparison = await api('/guesses', { puzzle_date: day, word: item.word });
    const actual = comparison.game.guesses[0];
    assert.equal(actual.similarity, item.similarity);
    assert.equal(actual.similarity_rank, item.rank);
    assert.equal(comparison.player_stats, null);
  }
  const comparisonCookie = cookie;
  const comparisonState = await api('/state');
  cookie = completedCookie;
  assert.deepEqual((await api('/state')).player_stats, stats);
  passed('완료 전 유사어 차단·실제 정답/중복/통계·1,000개 목록과 기준값 및 실제 입력 점수/순위 일치');

  progress('정답 후 친구 추측 기록의 접근 권한·입력 순서·실제 점수 비교');
  const historyPath = `/ranking/${comparisonState.user.id}/guesses?puzzle_date=${day}`;
  const ownPath = `/ranking/${state.user.id}/guesses?puzzle_date=${day}`;
  const visitor = await fetch(`${baseUrl}/api${historyPath}`);
  check(visitor.status === 401, '미등록 사용자가 친구 기록을 읽었습니다.');
  const unsolved = await fetch(`${baseUrl}/api${ownPath}`, { headers: { Cookie: comparisonCookie } });
  check(unsolved.status === 403, '미완료 사용자가 다른 사람의 정답 기록을 읽었습니다.');
  const snapshot = await databaseSnapshot(database);
  const history = await api(historyPath);
  assert.equal(history.status, 'playing');
  assert.equal(history.user.id, comparisonState.user.id);
  assert.equal(history.puzzle_date, day);
  assert.equal(history.attempts, 3);
  assert.deepEqual(history.guesses, [...comparisonState.game.guesses].sort((a, b) => a.attempt - b.attempt));
  assert.deepEqual(await databaseSnapshot(database), snapshot);
  cookie = comparisonCookie;
  await api('/guesses', { puzzle_date: day, word: related.words[0].word });
  const friendCompleted = await api('/guesses', { puzzle_date: day, word: answer });
  cookie = completedCookie;
  const solvedHistory = await api(historyPath);
  assert.equal(solvedHistory.status, 'completed');
  assert.equal(solvedHistory.attempts, 4);
  assert.deepEqual(solvedHistory.guesses, [...friendCompleted.game.guesses].sort((a, b) => a.attempt - b.attempt));
  assert.equal(solvedHistory.guesses.at(-1).is_correct, true);
  assert.equal(solvedHistory.guesses.at(-1).similarity_rank, 0);
  const reconnected = await api(historyPath);
  assert.deepEqual(reconnected, solvedHistory);
  assert.deepEqual((await api('/state')).player_stats, stats);
  passed('친구 기록: 미등록401·미완료403·완료 후 조회·최초 입력 순서·중복 보존·실제 점수/순위 일치·읽기 전용·재접속');
  summary.passed = true;
} catch (error) {
  summary.error = error instanceof CheckFailure ? error.message : `${stage}: ${error.name || '오류'}`;
  process.exitCode = 1;
} finally {
  cleaning = true;
  progress('검사 전용 컨테이너·DB·임시 설정 정리');
  try {
    check(/^ganmantle-check-[a-z0-9]+-[a-f0-9]{8}$/.test(project), '검사 프로젝트 이름 확인에 실패했습니다.');
    if (started) {
      await checkIsolation();
      await compose('down', '--volumes', '--remove-orphans');
      check(await docker(['ps', '-aq', '--filter', `label=com.docker.compose.project=${project}`]) === '', '검사 컨테이너가 남아 있습니다.');
      check(await docker(['volume', 'ls', '-q', '--filter', `label=com.docker.compose.project=${project}`]) === '', '검사 DB 볼륨이 남아 있습니다.');
      const remainingModel = await docker(['volume', 'inspect', modelVolume, '--format', '{{.Name}}']);
      check(remainingModel === modelVolume, '공유 모델 볼륨을 확인하지 못했습니다.');
      summary.cleanup.containers_and_database_removed = true;
      summary.cleanup.shared_model_preserved = true;
    }
  } catch (error) {
    summary.passed = false;
    summary.cleanup.error = error instanceof CheckFailure ? error.message : '검사 리소스 정리에 실패했습니다.';
    process.exitCode = 1;
  }
  try {
    for (const file of files) {
      const actual = await realpath(file);
      check(path.relative(await realpath(root), await realpath(output)) === 'test-results' &&
        path.relative(await realpath(output), actual) === path.basename(file), '임시 설정 삭제 경로가 검사 폴더 밖을 가리킵니다.');
      await rm(actual);
    }
    summary.cleanup.temporary_settings_removed = true;
  } catch {
    summary.passed = false;
    summary.cleanup.error = '임시 검사 설정을 정리하지 못했습니다. test-results의 이번 검사 파일을 확인하세요.';
    process.exitCode = 1;
  }
  process.removeListener('SIGINT', stop);
  process.removeListener('SIGTERM', stop);
  summary.finished_at = new Date().toISOString();
  await mkdir(output, { recursive: true });
  check(path.relative(await realpath(root), await realpath(output)) === 'test-results', '검사 결과 경로가 올바르지 않습니다.');
  await writeFile(path.join(output, 'release-checks.json'), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(summary, null, 2));
}
