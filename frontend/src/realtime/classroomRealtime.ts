import { Realtime, type ErrorInfo, type TokenRequest } from "ably";
import { Client } from "@stomp/stompjs";
import { bkquizApi } from "../api/bkquiz";
import { accessTokenStore } from "../auth/accessToken";

export type RealtimeProvider = "stomp" | "ably";

export function resolveRealtimeProvider(value: string | undefined): RealtimeProvider {
  return value?.trim().toLowerCase() === "ably" ? "ably" : "stomp";
}

export function classroomChannelName(classroomId: string): string {
  return `bkquiz:classroom:${classroomId}`;
}

interface ClassroomRealtimeOptions {
  classroomId: string;
  provider: RealtimeProvider;
  onEvent: () => void;
  onError?: (error: Error) => void;
}

export function subscribeToClassroomRealtime({
  classroomId,
  provider,
  onEvent,
  onError,
}: ClassroomRealtimeOptions): () => void {
  if (provider === "ably") {
    const client = new Realtime({
      authCallback: (_params, callback) => {
        void bkquizApi.realtimeToken(classroomId)
          .then((request) => callback(null, request satisfies TokenRequest))
          .catch((cause: unknown) => callback(
            (cause instanceof Error ? cause.message : "Không thể cấp quyền realtime.") as string,
            null,
          ));
      },
    });
    const channel = client.channels.get(classroomChannelName(classroomId));
    const listener = () => onEvent();
    void channel.subscribe("classroom-event", listener).catch((cause: unknown) => {
      onError?.(cause instanceof Error ? cause : new Error("Không thể kết nối Ably."));
    });
    client.connection.on("failed", (change) => {
      const reason = change.reason as ErrorInfo | undefined;
      onError?.(new Error(reason?.message ?? "Kết nối realtime bị gián đoạn."));
    });
    return () => {
      channel.unsubscribe("classroom-event", listener);
      client.channels.release(classroomChannelName(classroomId));
      client.close();
    };
  }

  const token = accessTokenStore.get();
  if (!token) return () => undefined;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const client = new Client({
    brokerURL: `${protocol}://${location.host}/ws`,
    connectHeaders: { Authorization: `Bearer ${token}` },
    reconnectDelay: 1000,
    maxReconnectDelay: 30000,
    onConnect: () => {
      client.subscribe(`/topic/classrooms/${classroomId}`, onEvent);
    },
    onStompError: (frame) => onError?.(new Error(frame.headers.message || "Kết nối STOMP lỗi.")),
  });
  client.activate();
  return () => {
    void client.deactivate();
  };
}
