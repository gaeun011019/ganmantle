// 전체·개인·단체 대화 팝업. 메시지는 서버에, 대화 선택과 방별 초안은 현재 탭에 보관합니다.
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { ApiError } from '../api';
import {
  chatRequest,
  GLOBAL_ROOM,
  type ChatMessage,
  type ChatRoom,
  type ChatUser,
  type Invitation,
  type MessagePage,
  type RoomList,
} from './api';

type Tab = ChatRoom['kind'];
type Outbox = { body: string; client_id: string };
type SavedChat = {
  tab: Tab;
  selection: Record<Tab, string | null>;
  drafts: Record<string, string>;
  outbox: Record<string, Outbox>;
};
const emptySaved = (): SavedChat => ({
  tab: 'global',
  selection: { global: GLOBAL_ROOM, group: null, direct: null },
  drafts: {},
  outbox: {},
});
function loadSaved(key: string): SavedChat {
  try {
    const raw = JSON.parse(sessionStorage.getItem(key) || 'null');
    const saved = emptySaved();
    if (!raw || typeof raw !== 'object') return saved;
    if (['global', 'group', 'direct'].includes(raw.tab)) saved.tab = raw.tab;
    for (const kind of ['group', 'direct'] as const)
      if (typeof raw.selection?.[kind] === 'string') saved.selection[kind] = raw.selection[kind];
    for (const [id, value] of Object.entries(raw.drafts || {}))
      if (typeof value === 'string' && value.length <= 1000) saved.drafts[id] = value;
    for (const [id, value] of Object.entries(raw.outbox || {})) {
      const item = value as Partial<Outbox> | null;
      if (
        typeof item?.body === 'string' &&
        item.body.length <= 1000 &&
        typeof item.client_id === 'string' &&
        /^[0-9a-f-]{36}$/i.test(item.client_id)
      )
        saved.outbox[id] = item as Outbox;
    }
    return saved;
  } catch {
    return emptySaved();
  }
}
function message(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : '채팅에 연결하지 못했어요. 다시 시도해 주세요.';
}
function mergeMessages(first: ChatMessage[], second: ChatMessage[]): ChatMessage[] {
  return [...new Map([...first, ...second].map((item) => [item.id, item])).values()].sort((a, b) =>
    BigInt(a.id) < BigInt(b.id) ? -1 : BigInt(a.id) > BigInt(b.id) ? 1 : 0,
  );
}
function timeLabel(value: string): string {
  return new Date(value).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

export default function ChatPanel({
  user,
  contact,
}: {
  user: ChatUser | null;
  contact: ChatUser | null;
}) {
  const storageKey = `ganmantle:chat:${user?.id || 'anonymous'}`;
  const [saved, setSavedState] = useState(() => loadSaved(storageKey));
  const savedRef = useRef(saved);
  // 저장을 effect나 React 갱신 함수에 미루지 않아 전송 직후 새로고침해도 같은 전송 ID를 씁니다.
  const setSaved = useCallback(
    (change: (previous: SavedChat) => SavedChat) => {
      const next = change(savedRef.current);
      savedRef.current = next;
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        /* 저장 차단 시 현재 화면 안에서 유지합니다. */
      }
      setSavedState(next);
    },
    [storageKey],
  );
  const [open, setOpen] = useState(false);
  const [rooms, setRooms] = useState<ChatRoom[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [pages, setPagesState] = useState<Record<string, MessagePage>>({});
  const pagesRef = useRef<Record<string, MessagePage>>({});
  const historyGeneration = useRef<Record<string, number>>({});
  // 비동기 응답끼리 비교할 최신 페이지를 즉시 반영합니다. React 갱신 함수 안에서 ref를 바꾸지 않습니다.
  const setRoomPage = useCallback((roomId: string, next: MessagePage) => {
    pagesRef.current = { ...pagesRef.current, [roomId]: next };
    setPagesState(pagesRef.current);
  }, []);
  const [roomErrors, setRoomErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [olderLoading, setOlderLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [connection, setConnection] = useState<'connecting' | 'live' | 'retrying' | 'offline'>(
    'connecting',
  );
  const [person, setPerson] = useState<ChatUser | null>(null);
  const [searchMode, setSearchMode] = useState<'direct' | 'create' | 'invite' | null>(null);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<ChatUser[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [invitees, setInvitees] = useState<ChatUser[]>([]);
  const [roomName, setRoomName] = useState('');
  const toggle = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const compose = useRef<HTMLTextAreaElement>(null);
  const history = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const listVersion = useRef(0);
  const messageVersions = useRef<Record<string, number>>({});
  const sendingNow = useRef(false);
  const activeId = saved.selection[saved.tab];
  const active = useRef(activeId);
  active.current = activeId;
  const selectedRoom = rooms.find((room) => room.id === activeId);
  const page = activeId ? pages[activeId] : undefined;
  const draft = activeId ? saved.drafts[activeId] || '' : '';

  useEffect(() => {
    if (!contact) return;
    setOpen(true);
    setPerson(contact);
    setNotice('');
  }, [contact]);
  useEffect(() => {
    if (!open) return;
    close.current?.focus({ preventScroll: true });
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        toggle.current?.focus({ preventScroll: true });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const loadRooms = useCallback(async () => {
    const version = ++listVersion.current;
    try {
      const result = await chatRequest<RoomList>('/rooms');
      if (version !== listVersion.current) return;
      setRooms(result.rooms);
      setInvitations(result.invitations);
      setError('');
      setSaved((previous) => {
        const selection = { ...previous.selection };
        for (const kind of ['group', 'direct'] as const)
          if (selection[kind] && !result.rooms.some((room) => room.id === selection[kind]))
            selection[kind] = null;
        return { ...previous, selection };
      });
    } catch (cause) {
      if (version === listVersion.current) setError(message(cause));
    }
  }, [setSaved]);
  const loadMessages = useCallback(
    async (roomId: string) => {
      const version = (messageVersions.current[roomId] || 0) + 1;
      messageVersions.current[roomId] = version;
      try {
        const result = await chatRequest<MessagePage>(
          `/rooms/${encodeURIComponent(roomId)}/messages?limit=50`,
        );
        if (messageVersions.current[roomId] !== version) return;
        const old = pagesRef.current[roomId];
        // 재접속 동안 50건 이상 늘어 중첩이 없으면 최신 페이지부터 이전 기록을 다시 읽습니다.
        const overlaps =
          old &&
          result.messages.some((item) => old.messages.some((existing) => existing.id === item.id));
        // 첫 조회보다 전송 응답이 먼저 온 경우에도 이전 기록의 커서를 잃지 않습니다.
        const containsOlder =
          old?.messages.length &&
          result.messages.length &&
          BigInt(old.messages[0].id) <= BigInt(result.messages[0].id);
        const keepHistory = old && (overlaps || result.messages.length === 0);
        if (!keepHistory)
          historyGeneration.current[roomId] = (historyGeneration.current[roomId] || 0) + 1;
        setRoomPage(
          roomId,
          keepHistory
            ? {
                messages: mergeMessages(old.messages, result.messages),
                next_before: containsOlder ? old.next_before : result.next_before,
              }
            : result,
        );
        setRoomErrors((previous) => ({ ...previous, [roomId]: '' }));
      } catch (cause) {
        if (messageVersions.current[roomId] === version)
          setRoomErrors((previous) => ({ ...previous, [roomId]: message(cause) }));
      }
    },
    [setRoomPage],
  );
  const catchUp = useCallback(() => {
    void loadRooms();
    if (active.current) void loadMessages(active.current);
  }, [loadRooms, loadMessages]);
  useEffect(() => {
    if (!open || !user) return;
    setConnection(navigator.onLine ? 'connecting' : 'offline');
    catchUp();
    const events = new EventSource('/api/chat/events');
    events.onopen = () => {
      setConnection('live');
      catchUp();
    };
    events.addEventListener('refresh', catchUp);
    events.onerror = () => setConnection(navigator.onLine ? 'retrying' : 'offline');
    const online = () => {
      setConnection('connecting');
      catchUp();
    };
    const offline = () => setConnection('offline');
    const visible = () => {
      if (!document.hidden) catchUp();
    };
    const retry = window.setInterval(() => {
      if (navigator.onLine && !document.hidden && events.readyState !== EventSource.OPEN) catchUp();
    }, 15000);
    window.addEventListener('online', online);
    window.addEventListener('offline', offline);
    document.addEventListener('visibilitychange', visible);
    return () => {
      events.close();
      window.clearInterval(retry);
      window.removeEventListener('online', online);
      window.removeEventListener('offline', offline);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [open, user?.id, catchUp]);
  useEffect(() => {
    if (!open || !user || !activeId) {
      setLoading(false);
      return;
    }
    stickToBottom.current = true;
    setLoading(true);
    void loadMessages(activeId).finally(() => {
      if (active.current === activeId) setLoading(false);
    });
  }, [open, user?.id, activeId, loadMessages]);
  useEffect(() => {
    if (open && stickToBottom.current)
      requestAnimationFrame(() => {
        if (history.current) history.current.scrollTop = history.current.scrollHeight;
      });
  }, [open, activeId, page?.messages.length]);
  useEffect(() => {
    let cancelled = false;
    setFound([]);
    setSearchError('');
    if (!searchMode || query.trim().length < 2) {
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => {
      void chatRequest<{ users: ChatUser[] }>(`/users?q=${encodeURIComponent(query.trim())}`)
        .then((result) => {
          if (!cancelled) setFound(result.users);
        })
        .catch((cause) => {
          if (!cancelled) setSearchError(message(cause));
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, searchMode]);

  function dismiss() {
    setOpen(false);
    toggle.current?.focus({ preventScroll: true });
  }
  function switchTab(tab: Tab) {
    setSaved((previous) => ({ ...previous, tab }));
    setSearchMode(null);
    setPerson(null);
    setQuery('');
    setInvitees([]);
    setNotice('');
  }
  function selectRoom(room: ChatRoom) {
    setSaved((previous) => ({
      ...previous,
      tab: room.kind,
      selection: { ...previous.selection, [room.kind]: room.id },
    }));
    stickToBottom.current = true;
    setSearchMode(null);
    setPerson(null);
    setNotice('');
  }
  function beginSearch(mode: 'direct' | 'create' | 'invite') {
    setSearchMode(mode);
    setQuery('');
    setInvitees([]);
    setPerson(null);
    setError('');
    setNotice('');
  }
  async function action(run: () => Promise<void>) {
    if (actionBusy) return;
    setActionBusy(true);
    setError('');
    setNotice('');
    try {
      await run();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setActionBusy(false);
    }
  }
  function startDirect() {
    if (!person) return;
    void action(async () => {
      const result = await chatRequest<{ room: ChatRoom }>('/direct', { user_id: person.id });
      setRooms((previous) => [
        ...previous.filter((room) => room.id !== result.room.id),
        result.room,
      ]);
      selectRoom(result.room);
      await loadRooms();
    });
  }
  function createRoom(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      const result = await chatRequest<{ room: ChatRoom }>('/rooms', {
        name: roomName.trim(),
        invitee_ids: invitees.map((item) => item.id),
      });
      setRooms((previous) => [...previous, result.room]);
      selectRoom(result.room);
      setRoomName('');
      setInvitees([]);
      setNotice('방을 만들었어요.');
      await loadRooms();
    });
  }
  function invitePeople() {
    if (!activeId || invitees.length === 0) return;
    const roomId = activeId;
    void action(async () => {
      for (const invitee of invitees)
        await chatRequest(`/rooms/${encodeURIComponent(roomId)}/invitations`, {
          user_id: invitee.id,
        });
      setSearchMode(null);
      setInvitees([]);
      setNotice('초대를 보냈어요.');
      await loadRooms();
    });
  }
  function answerInvitation(invitation: Invitation, accept: boolean) {
    void action(async () => {
      await chatRequest(`/invitations/${encodeURIComponent(invitation.room_id)}`, { accept });
      await loadRooms();
      if (accept)
        setSaved((previous) => ({
          ...previous,
          tab: 'group',
          selection: { ...previous.selection, group: invitation.room_id },
        }));
      setNotice(accept ? '초대를 수락했어요.' : '초대를 거절했어요.');
    });
  }
  async function loadOlder() {
    if (!activeId || !page?.next_before || olderLoading) return;
    const roomId = activeId;
    const cursor = pagesRef.current[roomId]?.next_before;
    if (!cursor) return;
    const generation = historyGeneration.current[roomId] || 0;
    const height = history.current?.scrollHeight || 0;
    stickToBottom.current = false;
    setOlderLoading(true);
    try {
      const result = await chatRequest<MessagePage>(
        `/rooms/${encodeURIComponent(roomId)}/messages?limit=50&before=${encodeURIComponent(cursor)}`,
      );
      if (
        (historyGeneration.current[roomId] || 0) !== generation ||
        pagesRef.current[roomId]?.next_before !== cursor
      ) {
        setRoomErrors((previous) => ({
          ...previous,
          [roomId]: '대화 목록이 갱신됐어요. 이전 메시지 더 보기를 다시 눌러 주세요.',
        }));
        return;
      }
      setRoomPage(roomId, {
        messages: mergeMessages(result.messages, pagesRef.current[roomId]?.messages || []),
        next_before: result.next_before,
      });
      requestAnimationFrame(() => {
        if (active.current === roomId && history.current)
          history.current.scrollTop += history.current.scrollHeight - height;
      });
    } catch (cause) {
      setRoomErrors((previous) => ({ ...previous, [roomId]: message(cause) }));
    } finally {
      setOlderLoading(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !user || sendingNow.current || !draft.trim() || !navigator.onLine) return;
    const roomId = activeId;
    const body = draft.trim().normalize('NFC');
    const pending = savedRef.current.outbox[roomId];
    const outgoing = pending?.body === body ? pending : { body, client_id: crypto.randomUUID() };
    sendingNow.current = true;
    setSending(true);
    setRoomErrors((previous) => ({ ...previous, [roomId]: '' }));
    setSaved((previous) => ({ ...previous, outbox: { ...previous.outbox, [roomId]: outgoing } }));
    try {
      const result = await chatRequest<{ message: ChatMessage }>(
        `/rooms/${encodeURIComponent(roomId)}/messages`,
        outgoing,
      );
      // 전송 전에 시작한 조회 응답이 방금 저장한 메시지를 가리지 않게 새 조회로 교체합니다.
      void loadMessages(roomId);
      setRoomPage(roomId, {
        messages: mergeMessages(pagesRef.current[roomId]?.messages || [], [result.message]),
        next_before: pagesRef.current[roomId]?.next_before || null,
      });
      setSaved((previous) => {
        const outbox = { ...previous.outbox };
        delete outbox[roomId];
        const drafts = { ...previous.drafts };
        if (drafts[roomId]?.trim().normalize('NFC') === body) drafts[roomId] = '';
        return { ...previous, drafts, outbox };
      });
      if (active.current === roomId) {
        stickToBottom.current = true;
        requestAnimationFrame(() => {
          compose.current?.focus({ preventScroll: true });
          if (history.current) history.current.scrollTop = history.current.scrollHeight;
        });
      }
    } catch (cause) {
      setRoomErrors((previous) => ({ ...previous, [roomId]: message(cause) }));
    } finally {
      sendingNow.current = false;
      setSending(false);
    }
  }
  function composeKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing &&
      event.nativeEvent.keyCode !== 229
    ) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const searchBox = searchMode && (
    <div className="chat-search">
      <label htmlFor="chat-search">
        {searchMode === 'direct' ? '대화할 닉네임 찾기' : '초대할 닉네임 찾기'}
      </label>
      <input
        id="chat-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.preventDefault();
        }}
        placeholder="닉네임 2자 이상"
        maxLength={20}
        autoComplete="off"
      />
      {searching && (
        <p className="chat-small" role="status">
          찾고 있어요…
        </p>
      )}
      {searchError && (
        <p className="chat-small chat-error" role="alert">
          {searchError}
        </p>
      )}
      {!searching && query.trim().length >= 2 && found.length === 0 && !searchError && (
        <p className="chat-small">일치하는 사용자가 없어요.</p>
      )}
      <ul className="chat-user-results">
        {found.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              disabled={actionBusy || invitees.some((selected) => selected.id === item.id)}
              onClick={() =>
                searchMode === 'direct'
                  ? setPerson(item)
                  : setInvitees((previous) => [...previous, item])
              }
            >
              {item.nickname}
              <span>{searchMode === 'direct' ? '선택' : '초대 대상 선택'}</span>
            </button>
          </li>
        ))}
      </ul>
      {invitees.length > 0 && (
        <ul className="chat-invitees">
          {invitees.map((item) => (
            <li key={item.id}>
              {item.nickname}
              <button
                type="button"
                aria-label={`${item.nickname} 선택 취소`}
                onClick={() =>
                  setInvitees((previous) => previous.filter((selected) => selected.id !== item.id))
                }
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <aside className="chat-dock" aria-label="채팅">
      {open && (
        <section className="chat-panel" id="chat-panel" role="dialog" aria-labelledby="chat-title">
          <div className="chat-heading">
            <h2 id="chat-title">채팅</h2>
            <button ref={close} className="chat-close" type="button" onClick={dismiss}>
              닫기
            </button>
          </div>
          {!user ? (
            <div className="chat-empty">
              <strong>닉네임을 먼저 정해 주세요</strong>
            </div>
          ) : (
            <>
              <div className="chat-tabs" aria-label="대화 종류">
                {(['global', 'group', 'direct'] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    className={saved.tab === tab ? 'selected' : ''}
                    aria-pressed={saved.tab === tab}
                    onClick={() => switchTab(tab)}
                  >
                    {tab === 'global'
                      ? '전체'
                      : tab === 'group'
                        ? `방${invitations.length ? ` (${invitations.length})` : ''}`
                        : '개인'}
                  </button>
                ))}
              </div>
              {(saved.tab === 'global' || selectedRoom) && (
                <p className="chat-context">
                  {saved.tab === 'global' ? '모두에게 공개되는 대화' : selectedRoom?.name}
                </p>
              )}
              <div className="chat-room-tools">
                {person && (
                  <div className="chat-person-action">
                    <span>{person.nickname} 님</span>
                    <button
                      type="button"
                      disabled={actionBusy || person.id === user.id}
                      onClick={startDirect}
                    >
                      대화하기
                    </button>
                    <button type="button" className="chat-link" onClick={() => setPerson(null)}>
                      취소
                    </button>
                  </div>
                )}
                {saved.tab !== 'global' && (
                  <div className="chat-room-picker">
                    <label className="sr-only" htmlFor="chat-room">
                      대화 선택
                    </label>
                    <select
                      id="chat-room"
                      value={activeId || ''}
                      onChange={(event) => {
                        const room = rooms.find((item) => item.id === event.target.value);
                        if (room) selectRoom(room);
                      }}
                    >
                      <option value="">
                        {saved.tab === 'group' ? '참여한 방 선택' : '개인 대화 선택'}
                      </option>
                      {rooms
                        .filter((room) => room.kind === saved.tab)
                        .map((room) => (
                          <option key={room.id} value={room.id}>
                            {room.name}
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      className="chat-link"
                      onClick={() => beginSearch(saved.tab === 'group' ? 'create' : 'direct')}
                    >
                      {saved.tab === 'group' ? '방 만들기' : '새 대화'}
                    </button>
                    {selectedRoom?.kind === 'group' && selectedRoom.owner_id === user.id && (
                      <button
                        type="button"
                        className="chat-link"
                        onClick={() => beginSearch('invite')}
                      >
                        초대
                      </button>
                    )}
                  </div>
                )}
                {saved.tab === 'group' && invitations.length > 0 && (
                  <div className="chat-invitations">
                    <h3>받은 초대</h3>
                    {invitations.map((invitation) => (
                      <div key={invitation.room_id}>
                        <p>
                          <strong>{invitation.room_name}</strong>
                          <span>{invitation.inviter_nickname} 님의 초대</span>
                        </p>
                        <button
                          type="button"
                          disabled={actionBusy}
                          onClick={() => answerInvitation(invitation, true)}
                        >
                          수락
                        </button>
                        <button
                          type="button"
                          className="chat-link"
                          disabled={actionBusy}
                          onClick={() => answerInvitation(invitation, false)}
                        >
                          거절
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {searchMode === 'create' ? (
                  <form className="chat-create" onSubmit={createRoom}>
                    <label htmlFor="chat-room-name">방 이름</label>
                    <input
                      id="chat-room-name"
                      value={roomName}
                      onChange={(event) => setRoomName(event.target.value)}
                      maxLength={40}
                      required
                      placeholder="1~40자"
                    />
                    {searchBox}
                    <div className="chat-form-actions">
                      <button type="submit" disabled={actionBusy || !roomName.trim()}>
                        방 만들고 초대
                      </button>
                      <button
                        type="button"
                        className="chat-link"
                        onClick={() => setSearchMode(null)}
                      >
                        취소
                      </button>
                    </div>
                  </form>
                ) : (
                  searchBox
                )}
                {searchMode === 'invite' && (
                  <div className="chat-form-actions">
                    <button
                      type="button"
                      disabled={actionBusy || invitees.length === 0}
                      onClick={invitePeople}
                    >
                      초대 보내기
                    </button>
                    <button type="button" className="chat-link" onClick={() => setSearchMode(null)}>
                      취소
                    </button>
                  </div>
                )}
                {error && (
                  <p className="chat-error" role="alert">
                    {error}
                    <button type="button" className="chat-link" onClick={catchUp}>
                      다시 연결
                    </button>
                  </p>
                )}
                {notice && (
                  <p className="chat-notice" role="status">
                    {notice}
                  </p>
                )}
              </div>
              <div
                ref={history}
                className="chat-messages"
                role="log"
                aria-label="대화 기록"
                aria-live="polite"
                aria-relevant="additions"
                onScroll={() => {
                  const element = history.current;
                  if (element)
                    stickToBottom.current =
                      element.scrollHeight - element.scrollTop - element.clientHeight < 50;
                }}
              >
                {page?.next_before && (
                  <button
                    type="button"
                    className="chat-older"
                    disabled={olderLoading}
                    onClick={() => void loadOlder()}
                  >
                    {olderLoading ? '불러오는 중…' : '이전 메시지 더 보기'}
                  </button>
                )}
                {loading && !page && (
                  <p className="chat-empty-message" role="status">
                    불러오는 중…
                  </p>
                )}
                {!activeId ? (
                  <p className="chat-empty-message">대화를 선택해 주세요.</p>
                ) : (
                  page?.messages.length === 0 && (
                    <p className="chat-empty-message">메시지가 없어요.</p>
                  )
                )}
                {page?.messages.map((item) => (
                  <article
                    key={item.id}
                    className={`chat-message${item.sender_id === user.id ? ' mine' : ''}`}
                  >
                    <div className="chat-message-meta">
                      {item.sender_id === user.id ? (
                        <span>나</span>
                      ) : (
                        <button
                          type="button"
                          className="chat-nickname"
                          onClick={() => setPerson({ id: item.sender_id, nickname: item.nickname })}
                        >
                          {item.nickname}
                        </button>
                      )}
                      <time
                        dateTime={item.created_at}
                        title={new Date(item.created_at).toLocaleString('ko-KR')}
                      >
                        {timeLabel(item.created_at)}
                      </time>
                    </div>
                    <p>{item.body}</p>
                  </article>
                ))}
              </div>
              {activeId && roomErrors[activeId] && (
                <p className="chat-error chat-send-error" role="alert">
                  {roomErrors[activeId]}
                  <button
                    type="button"
                    className="chat-link"
                    onClick={() => void loadMessages(activeId)}
                  >
                    기록 다시 확인
                  </button>
                </p>
              )}
              {connection !== 'live' && (
                <p className="chat-connection" role="status">
                  {connection === 'offline'
                    ? '인터넷 연결을 확인해 주세요.'
                    : connection === 'retrying'
                      ? '다시 연결 중…'
                      : '채팅에 연결 중…'}
                </p>
              )}
              <form className="chat-compose" onSubmit={send}>
                <label className="sr-only" htmlFor="chat-message">
                  메시지 입력
                </label>
                <textarea
                  ref={compose}
                  id="chat-message"
                  placeholder={activeId ? '메시지 입력' : '대화를 먼저 선택하세요'}
                  value={draft}
                  maxLength={1000}
                  rows={2}
                  onKeyDown={composeKey}
                  disabled={!activeId}
                  onChange={(event) => {
                    if (activeId)
                      setSaved((previous) => ({
                        ...previous,
                        drafts: { ...previous.drafts, [activeId]: event.target.value },
                      }));
                  }}
                />
                <button
                  type="submit"
                  disabled={!activeId || !draft.trim() || sending || connection === 'offline'}
                >
                  {sending ? '전송 중' : '보내기'}
                </button>
              </form>
            </>
          )}
        </section>
      )}
      <button
        ref={toggle}
        className="chat-toggle"
        type="button"
        aria-expanded={open}
        aria-controls={open ? 'chat-panel' : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? '채팅 닫기' : '채팅 열기'}
      </button>
    </aside>
  );
}
