# Caso de Uso — Servicios Inmobiliarios y Gestión de Propiedades

## 1. Dominio elegido
Servicios Inmobiliarios y Gestión de Propiedades

## 2. Nombre del asistente
Domus

## 3. Descripción del problema
La gestión inmobiliaria actual enfrenta una saturación operativa crítica derivada de la fragmentación en los canales de comunicación y la dependencia de procesos manuales para la calificación de prospectos y la coordinación de mantenimiento. Esta asincronía operativa no solo ralentiza los tiempos de respuesta, provocando la pérdida de oportunidades comerciales fuera del horario administrativo, sino que también genera una falta de trazabilidad que erosiona la confianza de los propietarios. Al implementar un agente inteligente, se resuelve esta ineficiencia mediante una capa de orquestación que automatiza el triaje de leads y la atención 24/7, permitiendo escalar la cartera de propiedades sin aumentar los costos operativos (OPEX) y transformando la interacción dispersa en un flujo de datos estructurado y estratégico para el negocio.

## 4. Perfil del usuario
La colección `clients` en Firestore contiene los siguientes campos:

```json
{
  "client_id": "client_001",
  "name": "Nombre del usuario",
  // Agrega aquí los campos específicos de tu dominio
}
```

## 5. Herramienta de búsqueda externa
- **API utilizada**: Tavily
- **Información que provee**: Proporciona datos del mercado inmobiliario en tiempo real, incluyendo fluctuaciones de precios en zonas específicas, comparativas de propiedades similares activas, actualizaciones en normativas municipales o leyes de arrendamiento vigentes, y geolocalización de servicios cercanos (colegios, transporte, comercios) para enriquecer la propuesta de valor de cada inmueble.
- **Cuándo se activa**: El agente invoca esta herramienta de forma autónoma cuando la consulta del usuario requiere datos dinámicos que no están presentes en la base de datos interna (RAG), tales como tendencias de inversión actuales, validación de requisitos legales de último minuto o cuando un prospecto solicita información contextual sobre el entorno geográfico de una propiedad.

## 6. System Prompt
```

Eres {nombre_asistente}, un asistente experto en {dominio}.

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
- Personaliza cada respuesta usando los datos del perfil del cliente.
- Usa el nombre del cliente cuando sea natural en la conversacion.
- Si el cliente busca opciones de mercado o precios actualizados,
  usa la herramienta de busqueda ANTES de responder.
- Prioriza recomendaciones accionables: zonas, rango de precios, y siguiente paso.
- Si faltan datos clave (presupuesto, zona o tipo), solicita esa informacion.
- Se conciso, claro y profesional.

```

## 7. Decisiones de diseño
FastAPI + SSE para streaming: Se eligió FastAPI por su soporte nativo de async/await y compatibilidad directa con Server-Sent Events (SSE) a través de sse-starlette. Esto permite transmitir tokens del LLM token a token al frontend sin bloquear el servidor, mejorando significativamente la experiencia de usuario en consultas de respuesta larga.

Firebase Firestore como base de datos: Firestore fue seleccionado por tres razones: (1) su modelo de documentos JSON se adapta naturalmente a perfiles de clientes con campos heterogéneos (arrays de preferencias, sub-objetos de historial), (2) ofrece SDK tanto síncrono como asíncrono, lo que permite usar el cliente async en los endpoints FastAPI y el cliente síncrono en el script de seed, y (3) la integración con Google Cloud elimina la necesidad de gestionar infraestructura de base de datos.

LangChain AgentExecutor con create_openai_tools_agent: Se optó por el patrón de tool-calling nativo de OpenAI (en lugar de ReAct) porque reduce la latencia al eliminar el ciclo de razonamiento explícito y es más determinista a la hora de decidir cuándo invocar la herramienta de búsqueda. El agente decide de forma autónoma si una consulta requiere datos en tiempo real antes de responder.

Perfil de cliente inyectado en el system prompt: En lugar de usar RAG sobre documentos, el perfil completo del cliente se inserta directamente en el system prompt en cada llamada. Esta decisión prioriza la simplicidad y la latencia: el contexto relevante siempre está disponible sin una etapa de recuperación vectorial, lo cual es apropiado dado el tamaño acotado del perfil.

Proxy Vite para CORS en desarrollo: El frontend React usa el proxy integrado de Vite (/api → localhost:8000) para evitar configuraciones de CORS complejas durante el desarrollo local. En producción, el origen del frontend se agrega directamente al middleware CORS de FastAPI.

Memoria persistente por conversación en Firestore: Cada conversación se almacena como un documento independiente en la colección conversations con un array de mensajes. Este diseño permite cargar el historial completo de una sesión anterior y continuar desde donde se dejó sin límite de conversaciones por cliente, y sin necesidad de mantener estado en el servidor.

## 8. Instrucciones de prueba
1. Selecciona el cliente `client_001` y envía: "¿Qué departamentos en Miraflores se ajustan a mi presupuesto y tienen cochera?"
2. Selecciona el cliente `client_002` y envía: "Necesito una casa en La Molina con jardín para trabajar desde casa, ¿qué opciones hay disponibles este mes?"
3. Envía una pregunta que requiera búsqueda en tiempo real: "¿Cuál es el precio promedio del metro cuadrado en Miraflores actualmente y cómo ha evolucionado en los últimos 6 meses?"
