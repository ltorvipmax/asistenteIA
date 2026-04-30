const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const BASE = API_BASE_URL || "/api";

export async function fetchClients() {
  const res = await fetch(`${BASE}/clients`);
  return res.json();
}

export async function fetchConversations(clientId) {
  const res = await fetch(`${BASE}/clients/${clientId}/conversations`);
  return res.json();
}

/**
 * Envía un mensaje con streaming SSE.
 * @param {string} clientId
 * @param {string} message
 * @param {string|null} conversationId
 * @param {function} onToken - callback por cada token recibido
 * @param {function} onToolCall - callback cuando el agente usa una herramienta
 * @param {function} onDone - callback al terminar, recibe conversationId
 * @param {function} onError - callback ante error del stream
 */
export function streamMessage(clientId, message, conversationId, onToken, onToolCall, onDone, onError) {
  const params = new URLSearchParams({
    client_id: clientId,
    message,
    ...(conversationId ? { conversation_id: conversationId } : {}),
  });

  const source = new EventSource(`${BASE}/agent/stream?${params}`);

  source.addEventListener("token", (e) => {
    const data = JSON.parse(e.data);
    onToken(data.content);
  });

  source.addEventListener("tool_call", (e) => {
    const data = JSON.parse(e.data);
    onToolCall(data.tool);
  });

  source.addEventListener("done", (e) => {
    const data = JSON.parse(e.data);
    source.close();
    onDone(data.conversation_id);
  });

  source.addEventListener("error", (e) => {
    let payload = {};
    try {
      payload = e?.data ? JSON.parse(e.data) : {};
    } catch {
      payload = {};
    }
    source.close();
    onError?.(payload);
  });

  return source;
}
