from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from agent.tools_langchain import search_real_time_info
from config import get_settings

SYSTEM_TEMPLATE = """
Eres Domus Asesor, un asistente experto en servicios inmobiliarios y propiedades.

CLIENTE: {name}
OBJETIVO DEL CLIENTE: {objetivo}
TIPO DE PROPIEDAD DE INTERES: {tipo_propiedad}
UBICACIONES PREFERIDAS: {ubicaciones_preferidas}
RANGO DE PRESUPUESTO USD: {presupuesto_min} - {presupuesto_max}
NUMERO DE HABITACIONES DESEADAS: {habitaciones_min}
PLAZO DE DECISION: {plazo_decision}
METODO DE FINANCIACION: {financiacion}
HISTORIAL RELEVANTE: {history}
NOTAS DEL ASESOR: {notes}

REGLAS:
- Responde de forma cordial, clara y profesional, sin sonar repetitivo.
- Sigue primero lo que el usuario dice en la conversacion actual.
- Usa los datos del perfil del cliente solo cuando ayuden a completar contexto, validar una recomendacion o advertir una inconsistencia.
- No presentes como dicho por el usuario ningun dato que provenga solo del perfil.
- Usa el nombre del cliente solo cuando sea natural en la conversacion, no en todos los turnos.
- Si el cliente busca opciones de mercado o precios actualizados,
  usa la herramienta de busqueda ANTES de responder.
- Prioriza recomendaciones accionables: zonas, rango de precios, y siguiente paso.
- Si faltan datos clave (presupuesto, zona o tipo), solicita esa informacion sin inventar valores.
- Si mencionas datos del perfil, deja claro que vienen del perfil base del cliente.
- Se conciso, claro y profesional.
"""


def build_system_prompt(client: dict) -> str:
    history_entries = client.get("history", [])
    normalized_history: list[str] = []
    for item in history_entries:
        if isinstance(item, str):
            normalized_history.append(item)
        elif isinstance(item, dict):
            role = item.get("role", "")
            content = item.get("content", "")
            if role and content:
                normalized_history.append(f"{role}: {content}")
            elif content:
                normalized_history.append(str(content))

    return SYSTEM_TEMPLATE.format(
        name=client.get("name", "Usuario"),
        objetivo=client.get("objetivo", ""),
        tipo_propiedad=client.get("tipo_propiedad", ""),
        ubicaciones_preferidas=", ".join(client.get("ubicaciones_preferidas", [])),
        presupuesto_min=client.get("presupuesto_min", ""),
        presupuesto_max=client.get("presupuesto_max", ""),
        habitaciones_min=client.get("habitaciones_min", ""),
        plazo_decision=client.get("plazo_decision", ""),
        financiacion=client.get("financiacion", ""),
        history=" | ".join(normalized_history),
        notes=client.get("notes", ""),
    )


def build_chat_history(messages: list[dict]) -> list:
    history = []
    for msg in messages:
        if msg["role"] == "human":
            history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "ai":
            history.append(AIMessage(content=msg["content"]))
    return history


class CompatibleAgent:
    """Compatibilidad con la interfaz usada por los routers sin AgentExecutor."""

    def __init__(self, llm_with_tools, system_prompt: str):
        self.llm_with_tools = llm_with_tools
        self.system_prompt = system_prompt

    async def _collect_streamed_message(self, messages: list, *, emit_chunks: bool):
        aggregated = None

        async for chunk in self.llm_with_tools.astream(messages):
            aggregated = chunk if aggregated is None else aggregated + chunk
            content = getattr(chunk, "content", "")
            if emit_chunks and content:
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": content},
                }

        if aggregated is None:
            return

        yield {
            "event": "_message_complete",
            "data": {"message": aggregated},
        }

    async def _run_with_streaming(self, user_input: str, chat_history: list, emit_chunks: bool):
        messages = [
            SystemMessage(content=self.system_prompt),
            *chat_history,
            HumanMessage(content=user_input),
        ]

        first_message = None
        async for event in self._collect_streamed_message(messages, emit_chunks=emit_chunks):
            if event["event"] == "_message_complete":
                first_message = event["data"]["message"]
                continue
            yield event

        if first_message is None:
            yield {
                "event": "_run_complete",
                "data": {"output": "", "tool_names": []},
            }
            return

        tool_names: list[str] = []
        tool_calls = getattr(first_message, "tool_calls", None) or []
        if tool_calls:
            messages.append(first_message)

            for tc in tool_calls:
                tool_name = tc.get("name", "search_real_time_info")
                tool_names.append(tool_name)
                yield {
                    "event": "on_tool_start",
                    "name": tool_name,
                    "data": {},
                }

                args = tc.get("args", {})
                if isinstance(args, dict):
                    query = args.get("query") or str(args)
                else:
                    query = str(args)

                tool_result = await search_real_time_info.ainvoke({"query": query})
                messages.append(
                    ToolMessage(
                        content=tool_result,
                        tool_call_id=tc.get("id", "tool_call"),
                    )
                )

            final_message = None
            async for event in self._collect_streamed_message(messages, emit_chunks=emit_chunks):
                if event["event"] == "_message_complete":
                    final_message = event["data"]["message"]
                    continue
                yield event

            output = str(getattr(final_message, "content", "")) if final_message is not None else ""
            yield {
                "event": "_run_complete",
                "data": {"output": output, "tool_names": tool_names},
            }
            return

        output = str(getattr(first_message, "content", ""))
        yield {
            "event": "_run_complete",
            "data": {"output": output, "tool_names": tool_names},
        }

    async def _run(self, user_input: str, chat_history: list) -> tuple[str, list[str]]:
        output = ""
        tool_names: list[str] = []
        async for event in self._run_with_streaming(user_input, chat_history, emit_chunks=False):
            if event["event"] != "_run_complete":
                continue
            output = event["data"]["output"]
            tool_names = event["data"]["tool_names"]
        return output, tool_names

    async def ainvoke(self, payload: dict) -> dict:
        output, _ = await self._run(
            user_input=payload.get("input", ""),
            chat_history=payload.get("chat_history", []),
        )
        return {"output": output}

    async def astream_events(self, payload: dict, version: str = "v2"):
        _ = version
        async for event in self._run_with_streaming(
            user_input=payload.get("input", ""),
            chat_history=payload.get("chat_history", []),
            emit_chunks=True,
        ):
            if event["event"] == "_run_complete":
                continue
            yield event


def create_agent(client: dict) -> CompatibleAgent:
    settings = get_settings()
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=settings.openai_api_key,
        temperature=0.7,
        streaming=True,
        timeout=20,
        max_retries=0,
    )
    llm_with_tools = llm.bind_tools([search_real_time_info])
    return CompatibleAgent(
        llm_with_tools=llm_with_tools,
        system_prompt=build_system_prompt(client),
    )
