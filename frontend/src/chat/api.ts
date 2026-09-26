// 채팅 API 타입과 요청. 게임 응답과 별도로 다루며 세션 쿠키로 권한을 확인합니다.
import { ApiError } from '../api';
export type ChatUser = { id: string; nickname: string };
export type ChatRoom = { id: string; kind: 'global' | 'direct' | 'group'; name: string; owner_id: string | null };
export type Invitation = { room_id: string; room_name: string; inviter_nickname: string };
export type ChatMessage = { id: string; room_id: string; sender_id: string; nickname: string; body: string; created_at: string };
export type MessagePage = { messages: ChatMessage[]; next_before: string | null };
export type RoomList = { rooms: ChatRoom[]; invitations: Invitation[] };
export const GLOBAL_ROOM = '00000000-0000-0000-0000-000000000001';

export async function chatRequest<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/chat${path}`, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new ApiError(response.status, 'invalid_response', '채팅 응답을 확인하지 못했어요. 잠시 후 다시 시도해 주세요.'); }
  if (!response.ok) throw new ApiError(response.status, data.detail?.code || 'chat_failed',
    typeof data.detail?.message === 'string' ? data.detail.message : '채팅 요청을 처리하지 못했어요. 다시 확인해 주세요.');
  return data as T;
}
