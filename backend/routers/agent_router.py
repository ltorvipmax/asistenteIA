import asyncio
import json
import os
import re
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from firebase.clients import get_client
from firebase.chat_history import (
    create_conversation, get_conversation,
    add_message
)
from agent.agent import create_agent, build_chat_history
from config import get_settings
from schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/agent", tags=["agent"])
AGENT_TIMEOUT_SECONDS = 6
KNOWN_ZONES = [
    "Miraflores",
    "San Isidro",
    "Barranco",
    "Surco",
    "La Molina",
    "San Borja",
    "Jesus Maria",
    "Centro Financiero",
]
FOLLOW_UP_MARKERS = {
    "precio",
    "precios",
    "espacio",
    "metraje",
    "metros",
    "m2",
    "ubicacion",
    "ubicación",
    "zona",
    "zonas",
    "alternativas",
    "opciones",
    "barato",
    "barata",
    "caro",
    "cara",
    "cuota",
    "financiamiento",
    "dormitorios",
    "habitaciones",
}
SPACE_MARKERS = {"espacio", "metraje", "metros", "m2", "amplitud", "grande", "grandes"}
PRICE_MARKERS = {"precio", "precios", "barato", "barata", "caro", "cara", "cuota", "presupuesto"}
LOCATION_MARKERS = {"ubicacion", "ubicación", "zona", "zonas", "barrio", "distrito"}


def _extract_budget(user_message: str) -> int | None:
    match = re.search(
        r"(?:presupuesto(?:\s+de)?|hasta|max(?:imo)?|usd|us\$|\$)\s*([\d][\d,\.]*)",
        user_message,
        re.IGNORECASE,
    )
    if not match:
        for candidate in re.findall(r"\b\d[\d,\.]{3,}\b", user_message):
            digits = re.sub(r"[^\d]", "", candidate)
            if digits:
                return int(digits)
        return None

    digits = re.sub(r"[^\d]", "", match.group(1))
    return int(digits) if digits else None


def _extract_rooms(user_message: str) -> int | None:
    match = re.search(r"(\d+)\s*(?:cuartos?|habitaciones?|dormitorios?)", user_message, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _detect_property_type(user_message: str, client: dict) -> str:
    lowered = user_message.lower()
    if "casa" in lowered:
        return "casa"
    if "departamento" in lowered or "depa" in lowered:
        return "departamento"
    if "local" in lowered:
        return "local comercial"
    return client.get("tipo_propiedad", "propiedad")


def _detect_explicit_property_type(user_message: str) -> str | None:
    lowered = user_message.lower()
    if "casa" in lowered:
        return "casa"
    if "departamento" in lowered or "depa" in lowered:
        return "departamento"
    if "local" in lowered:
        return "local comercial"
    return None


def _detect_zones(user_message: str, client: dict) -> list[str]:
    lowered = user_message.lower()
    zones = [zone for zone in KNOWN_ZONES if zone.lower() in lowered]
    if zones:
        return zones
    return client.get("ubicaciones_preferidas", [])[:3]


def _detect_explicit_zones(user_message: str) -> list[str]:
    lowered = user_message.lower()
    return [zone for zone in KNOWN_ZONES if zone.lower() in lowered]


def _article_for(property_type: str) -> str:
    return "una" if property_type in {"casa", "propiedad"} else "un"


def _should_use_live_agent() -> bool:
    override = os.getenv("USE_LIVE_AGENT")
    if override == "1":
        return True

    return bool(get_settings().openai_api_key)


def _is_market_realtime_request(user_message: str) -> bool:
    lowered = user_message.lower()
    markers = [
        "hoy",
        "actual",
        "actualizado",
        "mercado",
        "internet",
        "noticia",
        "tendencia",
        "busca",
        "buscar",
        "precio actual",
    ]
    return any(m in lowered for m in markers)


def _is_structured_profile_request(user_message: str) -> bool:
    lowered = user_message.lower().strip()
    if not lowered:
        return False

    has_zone = any(zone.lower() in lowered for zone in KNOWN_ZONES)
    has_rooms = _extract_rooms(user_message) is not None
    has_budget = _extract_budget(user_message) is not None
    has_property = any(word in lowered for word in ["depa", "departamento", "casa", "local"])
    compact_request = len(lowered) <= 120

    return compact_request and (has_zone or has_rooms or has_budget or has_property)


def _combined_recent_human_context(messages: list[dict] | None, user_message: str, max_items: int = 3) -> str:
    recent_human_messages: list[str] = []
    for item in (messages or []):
        if item.get("role") != "human":
            continue
        content = str(item.get("content", "")).strip()
        if content:
            recent_human_messages.append(content)

    combined = recent_human_messages[-max_items:]
    if user_message.strip():
        combined.append(user_message.strip())
    return " ".join(combined)


def _is_follow_up_profile_request(user_message: str, messages: list[dict] | None) -> bool:
    lowered = user_message.lower().strip()
    if not lowered or len(lowered) > 40:
        return False

    if _is_structured_profile_request(user_message):
        return False

    has_follow_up_marker = any(marker in lowered for marker in FOLLOW_UP_MARKERS)
    if not has_follow_up_marker:
        return False

    recent_context = _combined_recent_human_context(messages, user_message)
    return _is_structured_profile_request(recent_context)


def _chunk_text(text: str, chunk_size: int = 32) -> list[str]:
    if not text:
        return []
    return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]


def _detect_follow_up_focus(user_message: str) -> str | None:
    lowered = user_message.lower().strip()
    if not lowered:
        return None

    if any(marker in lowered for marker in SPACE_MARKERS):
        return "space"
    if any(marker in lowered for marker in PRICE_MARKERS):
        return "price"
    if any(marker in lowered for marker in LOCATION_MARKERS):
        return "location"
    return None


def _focused_follow_up_response(
    *,
    focus: str,
    client: dict,
    property_type: str,
    zones: list[str],
    target_budget: int | None,
    explicit_budget: int | None,
    target_rooms: int | None,
    explicit_rooms: int | None,
) -> str:
    zone_text = ", ".join(zones) if zones else "las zonas de tu interés"
    budget_text = f"USD {explicit_budget:,}" if explicit_budget else "tu rango objetivo"

    if focus == "space":
        room_text = f"de {explicit_rooms} cuartos " if explicit_rooms else ""
        return (
            f"Si tu prioridad es el espacio, en {zone_text} conviene concentrarse en {property_type}s {room_text}"
            f"con distribución eficiente y más metraje útil, aunque a {budget_text} probablemente tengas que aceptar edificio más antiguo,"
            " menos acabados premium o alejarte unas cuadras de las zonas más demandadas. Si quieres, te planteo ahora mismo 3 opciones"
            " priorizando espacio por encima de ubicación y precio."
        )

    if focus == "price":
        return (
            f"Si lo más importante es el precio, en {zone_text} lo razonable es filtrar {property_type}s dentro de {budget_text}"
            " priorizando oportunidad de compra, edificio con más años o menor cercanía a ejes premium. Si quieres, te propongo 3 alternativas"
            " ordenadas de la más económica a la más equilibrada."
        )

    if focus == "location":
        return (
            f"Si tu prioridad es la ubicación, en {zone_text} conviene mantenerte en los sectores con mejor acceso y demanda, aunque eso"
            f" normalmente obliga a ser más estricto con metraje o presupuesto alrededor de {budget_text}. Si quieres, te doy 3 alternativas centradas"
            " en ubicación antes que en espacio o precio."
        )

    return ""


def _fallback_response(client: dict, user_message: str, messages: list[dict] | None = None) -> str:
    quick_msg = user_message.strip().lower()
    name = client.get("name", "cliente")
    if quick_msg in {"hola", "hi", "hello", "buenas", "buenos dias", "buenas tardes", "buenas noches"}:
        zones = ", ".join(client.get("ubicaciones_preferidas", [])[:3]) or "tus zonas de preferencia"
        return (
            f"Hola {name}. Ya tengo tu perfil cargado. "
            f"Puedo orientarte en {zones} dentro de tu rango objetivo. "
            "Dime presupuesto, tipo de propiedad y cuántos cuartos necesitas para darte una recomendación concreta."
        )

    context_message = _combined_recent_human_context(messages, user_message)
    explicit_property_type = _detect_explicit_property_type(context_message)
    explicit_zones = _detect_explicit_zones(context_message)
    explicit_budget = _extract_budget(context_message)
    explicit_rooms = _extract_rooms(context_message)
    budget = explicit_budget
    rooms = explicit_rooms
    property_type = explicit_property_type or client.get("tipo_propiedad", "propiedad")
    zones = explicit_zones or client.get("ubicaciones_preferidas", [])[:3]
    zone_text = ", ".join(zones) if zones else "las zonas de tu interés"

    profile_min = client.get("presupuesto_min")
    profile_max = client.get("presupuesto_max")
    target_budget = budget or profile_max or profile_min
    profile_type = client.get("tipo_propiedad", "propiedad")
    target_rooms = rooms or client.get("habitaciones_min")
    follow_up_focus = _detect_follow_up_focus(user_message)

    if follow_up_focus and messages:
        focused_response = _focused_follow_up_response(
            focus=follow_up_focus,
            client=client,
            property_type=property_type,
            zones=zones,
            target_budget=target_budget,
            explicit_budget=explicit_budget,
            target_rooms=target_rooms,
            explicit_rooms=explicit_rooms,
        )
        if focused_response:
            return focused_response

    profile_notes: list[str] = []
    if not explicit_property_type and client.get("tipo_propiedad"):
        profile_notes.append(f"en tu perfil base aparece {client['tipo_propiedad']}")
    if not explicit_zones and client.get("ubicaciones_preferidas"):
        base_zones = ", ".join(client.get("ubicaciones_preferidas", [])[:3])
        if base_zones:
            profile_notes.append(f"tu perfil prioriza {base_zones}")
    if not explicit_budget and client.get("presupuesto_min") and client.get("presupuesto_max"):
        profile_notes.append(
            f"tu perfil base maneja un rango de USD {client['presupuesto_min']:,}-{client['presupuesto_max']:,}"
        )

    missing_fields: list[str] = []
    if not explicit_property_type:
        missing_fields.append("tipo de propiedad")
    if not explicit_budget:
        missing_fields.append("presupuesto")
    if not explicit_rooms:
        missing_fields.append("cuántos cuartos necesitas")
    if not explicit_zones:
        missing_fields.append("zona")

    if missing_fields:
        provided_bits: list[str] = []
        if explicit_property_type:
            provided_bits.append(explicit_property_type)
        if explicit_zones:
            provided_bits.append(zone_text)
        if explicit_budget:
            provided_bits.append(f"USD {explicit_budget:,}")
        if explicit_rooms:
            provided_bits.append(f"{explicit_rooms} cuartos")

        if provided_bits:
            provided_text = ", ".join(provided_bits)
            profile_hint = f" Si te sirve como referencia, {'. '.join(profile_notes)}." if profile_notes else ""
            return (
                f"Tomo como referencia {provided_text}. Para aconsejarte mejor sin asumir datos de tu perfil, todavía necesito "
                f"{', '.join(missing_fields)}.{profile_hint}"
            )

        profile_hint = f" Si te sirve como referencia, {'. '.join(profile_notes)}." if profile_notes else ""
        return (
            "Puedo orientarte mejor si me dices zona, presupuesto, tipo de propiedad y cuántos cuartos buscas. "
            f"Prefiero no asumir esos datos sólo por tu perfil.{profile_hint}"
        )

    intro = f"Para buscar {_article_for(property_type)} {property_type}"
    if target_rooms:
        intro += f" de {target_rooms} cuartos"
    intro += f" en {zone_text}"
    if target_budget:
        intro += f" con un presupuesto de USD {target_budget:,}"
    intro += ", esto es lo más realista hoy:"

    insights: list[str] = []
    if profile_min and budget and budget < profile_min:
        insights.append(
            f"tu presupuesto actual está por debajo de tu rango perfilado de USD {profile_min:,}-{profile_max:,} para esas zonas"
        )
    elif profile_max and budget and budget > profile_max:
        insights.append(
            f"tu presupuesto supera tu rango inicial de USD {profile_min:,}-{profile_max:,}, así que podemos apuntar a opciones premium o con más metraje"
        )
    elif profile_min and profile_max:
        insights.append(
            f"tu rango perfilado de USD {profile_min:,}-{profile_max:,} sí encaja con una búsqueda enfocada en {zone_text}"
        )

    if property_type != profile_type:
        insights.append(
            f"tu perfil venía orientado a {profile_type}, así que cambiar a {property_type} probablemente exigirá ajustar zona o presupuesto"
        )

    if target_rooms and isinstance(target_rooms, int) and target_rooms >= 4 and zones:
        insights.append(
            "una propiedad de 4 cuartos o más en esas zonas suele ser bastante más escasa, por lo que conviene priorizar entre ubicación, metraje y presupuesto"
        )

    if not insights:
        insights.append(
            "con los datos que me diste ya puedo proponerte una búsqueda bastante afinada"
        )

    detail_text = "; ".join(insights[:2])
    if detail_text:
        detail_text = detail_text[0].upper() + detail_text[1:] + "."

    next_step = "Si quieres, en el siguiente mensaje te propongo 3 alternativas concretas"
    if zones:
        next_step += f" para {zone_text}"
    if target_budget:
        next_step += f" alrededor de USD {target_budget:,}"
    next_step += ", indicando cuál prioriza precio, cuál ubicación y cuál espacio."

    return f"{intro} {detail_text} {next_step}"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint no-streaming para pruebas rápidas."""
    client = await get_client(request.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if not request.conversation_id:
        conversation_id = await create_conversation(request.client_id)
    else:
        conversation_id = request.conversation_id

    conv = await get_conversation(conversation_id)
    raw_messages = (conv or {}).get("messages", [])
    history = build_chat_history(raw_messages)

    human_write_task = asyncio.create_task(
        add_message(conversation_id, request.client_id, "human", request.message)
    )

    response_text = ""
    quick_msg = request.message.strip().lower()
    use_live_agent = _should_use_live_agent()
    use_fast_fallback = (
        quick_msg in {"hola", "hi", "hello", "buenas", "buenos dias", "buenas tardes", "buenas noches"}
        or (_is_structured_profile_request(request.message) and not _is_market_realtime_request(request.message))
        or _is_follow_up_profile_request(request.message, raw_messages)
    )

    if (not use_live_agent) or use_fast_fallback:
        response_text = _fallback_response(client, request.message, raw_messages)
    else:
        try:
            agent = create_agent(client)
            task = asyncio.create_task(agent.ainvoke({
                "input": request.message,
                "chat_history": history
            }))
            done, _ = await asyncio.wait({task}, timeout=AGENT_TIMEOUT_SECONDS)
            if task in done:
                result = task.result()
                response_text = result.get("output", "")
            else:
                task.cancel()
                response_text = _fallback_response(client, request.message, raw_messages)
        except Exception:
            response_text = _fallback_response(client, request.message, raw_messages)

    asyncio.create_task(add_message(conversation_id, request.client_id, "ai", response_text))

    return ChatResponse(response=response_text, conversation_id=conversation_id)


@router.get("/stream")
async def stream(
    client_id: str,
    message: str,
    conversation_id: str = None
):
    """Endpoint SSE con streaming de tokens."""
    client = await get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if not conversation_id:
        conversation_id = await create_conversation(client_id)

    conv = await get_conversation(conversation_id)
    raw_messages = (conv or {}).get("messages", [])
    history = build_chat_history(raw_messages)

    human_write_task = asyncio.create_task(add_message(conversation_id, client_id, "human", message))

    async def event_generator():
        full_response = ""
        try:
            quick_msg = message.strip().lower()
            use_live_agent = _should_use_live_agent()
            use_fast_fallback = (
                quick_msg in {"hola", "hi", "hello", "buenas", "buenos dias", "buenas tardes", "buenas noches"}
                or (_is_structured_profile_request(message) and not _is_market_realtime_request(message))
                or _is_follow_up_profile_request(message, raw_messages)
            )

            if (not use_live_agent) or use_fast_fallback:
                full_response = _fallback_response(client, message, raw_messages)
            else:
                agent = create_agent(client)
                streamed_any_token = False
                stream_error = None

                try:
                    async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                        async for event in agent.astream_events({
                            "input": message,
                            "chat_history": history
                        }):
                            if event.get("event") == "on_tool_start":
                                yield {
                                    "event": "tool_call",
                                    "data": json.dumps({"tool": event.get("name", "tool")})
                                }
                                continue

                            if event.get("event") != "on_chat_model_stream":
                                continue

                            chunk = event.get("data", {}).get("chunk", "")
                            if not chunk:
                                continue

                            streamed_any_token = True
                            full_response += str(chunk)
                            yield {
                                "event": "token",
                                "data": json.dumps({"content": str(chunk)})
                            }
                except Exception as exc:
                    stream_error = exc

                if stream_error and not streamed_any_token:
                    full_response = _fallback_response(client, message, raw_messages)
                    for chunk in _chunk_text(full_response):
                        yield {
                            "event": "token",
                            "data": json.dumps({"content": chunk})
                        }

            asyncio.create_task(add_message(conversation_id, client_id, "ai", full_response))
            yield {
                "event": "done",
                "data": json.dumps({"conversation_id": conversation_id})
            }

        except Exception as e:
            fallback = _fallback_response(client, message, raw_messages)
            try:
                await add_message(conversation_id, client_id, "ai", fallback)
            except Exception:
                pass
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e), "fallback": fallback})
            }

    return EventSourceResponse(
        event_generator(),
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )
