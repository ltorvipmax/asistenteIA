import { useState, useEffect, useRef } from "react";
import { fetchClients, fetchConversations, streamMessage } from "./api";

export default function App() {
  const [clients, setClients] = useState([]);
  const [loadingClients, setLoadingClients] = useState(true);
  const [clientsError, setClientsError] = useState("");
  const [selectedClient, setSelectedClient] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const messagesEndRef = useRef(null);

  const loadClientConversations = async (clientId) => {
    const convs = await fetchConversations(clientId);
    const normalized = Array.isArray(convs) ? convs : [];
    setConversations(normalized);
  };

  const loadClients = async () => {
    setLoadingClients(true);
    setClientsError("");
    try {
      const data = await fetchClients();
      setClients(Array.isArray(data) ? data : []);
    } catch (error) {
      setClients([]);
      setClientsError("No se pudo conectar al backend. Reintenta en unos segundos.");
      console.error(error);
    } finally {
      setLoadingClients(false);
    }
  };

  // Carga la lista de clientes al iniciar
  useEffect(() => {
    loadClients();
  }, []);

  // Scroll automático al último mensaje
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const selectClient = async (client) => {
    setSelectedClient(client);
    setMessages([]);
    setConversationId(null);
    setConversations([]);
  };

  useEffect(() => {
    if (!selectedClient) {
      return;
    }

    loadClientConversations(selectedClient.client_id).catch((error) => {
      console.error(error);
      setConversations([]);
    });
  }, [selectedClient]);

  const loadConversation = (conv) => {
    setConversationId(conv.conversation_id);
    setMessages(conv.messages || []);
  };

  const sendMessage = () => {
    if (!input.trim() || !selectedClient || isStreaming) return;

    const userMessage = { role: "human", content: input };
    setMessages((prev) => [...prev, userMessage, { role: "ai", content: "" }]);
    setInput("");
    setIsStreaming(true);
    setActiveTool(null);

    streamMessage(
      selectedClient.client_id,
      input,
      conversationId,
      (token) => {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: updated[updated.length - 1].content + token,
          };
          return updated;
        });
      },
      (tool) => setActiveTool(tool),
      (newConvId) => {
        setConversationId(newConvId);
        setIsStreaming(false);
        setActiveTool(null);
        loadClientConversations(selectedClient.client_id).catch(console.error);
      },
      (errorPayload) => {
        const fallback =
          errorPayload?.fallback ||
          "No pude responder en este momento (timeout o red). Intenta de nuevo.";

        setMessages((prev) => {
          const updated = [...prev];
          if (updated.length > 0 && updated[updated.length - 1].role === "ai") {
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: updated[updated.length - 1].content || fallback,
            };
          }
          return updated;
        });

        setIsStreaming(false);
        setActiveTool(null);
      }
    );
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "sans-serif" }}>
      {/* Sidebar — Clientes */}
      <div style={{ width: 240, borderRight: "1px solid #ddd", padding: 16, overflowY: "auto" }}>
        <h3 style={{ margin: "0 0 12px" }}>Clientes</h3>
        {loadingClients && <p style={{ fontSize: 12, color: "#666" }}>Cargando clientes...</p>}
        {!loadingClients && clientsError && (
          <div style={{ marginBottom: 10 }}>
            <p style={{ fontSize: 12, color: "#b42318", margin: "0 0 8px" }}>{clientsError}</p>
            <button
              onClick={loadClients}
              style={{
                padding: "6px 10px",
                borderRadius: 6,
                border: "1px solid #ccc",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              Reintentar
            </button>
          </div>
        )}
        {clients.map((c) => (
          <div
            key={c.client_id}
            onClick={() => selectClient(c)}
            style={{
              padding: "8px 12px",
              marginBottom: 6,
              cursor: "pointer",
              borderRadius: 6,
              background: selectedClient?.client_id === c.client_id ? "#e0f0ff" : "#f5f5f5",
              fontWeight: selectedClient?.client_id === c.client_id ? "bold" : "normal",
            }}
          >
            {c.name}
          </div>
        ))}

        {selectedClient && conversations.length > 0 && (
          <>
            <h4 style={{ margin: "16px 0 8px" }}>Historial</h4>
            {conversations.map((conv) => (
              <div
                key={conv.conversation_id}
                onClick={() => loadConversation(conv)}
                style={{
                  padding: "6px 10px",
                  marginBottom: 4,
                  cursor: "pointer",
                  borderRadius: 4,
                  fontSize: 12,
                  background: conversationId === conv.conversation_id ? "#d0e8ff" : "#eee",
                }}
              >
                {conv.conversation_id.slice(0, 8)}... ({(conv.messages || []).length} msgs)
              </div>
            ))}
          </>
        )}
      </div>

      {/* Chat */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ padding: 16, borderBottom: "1px solid #ddd", background: "#fafafa" }}>
          <h2 style={{ margin: 0 }}>
            {selectedClient ? `Chat con ${selectedClient.name}` : "Selecciona un cliente"}
          </h2>
          {activeTool && (
            <span style={{ fontSize: 12, color: "#888" }}>🔍 Buscando: {activeTool}...</span>
          )}
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: msg.role === "human" ? "flex-end" : "flex-start",
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  maxWidth: "70%",
                  padding: "10px 14px",
                  borderRadius: 12,
                  background: msg.role === "human" ? "#0078d4" : "#f0f0f0",
                  color: msg.role === "human" ? "white" : "black",
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg.content || (isStreaming && i === messages.length - 1 ? "▌" : "")}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {selectedClient && (
          <div style={{ padding: 16, borderTop: "1px solid #ddd", display: "flex", gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
              placeholder="Escribe un mensaje..."
              disabled={isStreaming}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: 8,
                border: "1px solid #ddd",
                fontSize: 14,
              }}
            />
            <button
              onClick={sendMessage}
              disabled={isStreaming || !input.trim()}
              style={{
                padding: "10px 20px",
                borderRadius: 8,
                border: "none",
                background: isStreaming ? "#ccc" : "#0078d4",
                color: "white",
                cursor: isStreaming ? "not-allowed" : "pointer",
                fontSize: 14,
              }}
            >
              {isStreaming ? "..." : "Enviar"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
