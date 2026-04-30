# Servicios Inmobiliarios y Gestión de Propiedades — Asistente IA

Asistente conversacional construido con FastAPI + LangChain + Firebase Firestore + React.

## Requisitos

- Python 3.11+
- Node.js 18+
- Cuenta Firebase (Firestore habilitado)
- API Keys: OpenAI y Tavily

## Setup Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configura credenciales
cp .env.example .env
# Edita .env con tus API keys
# Coloca firebase-service-account.json en backend/

# Carga datos iniciales
python seed.py

# Inicia el servidor
uvicorn main:app --reload --port 8000
```

## Setup Frontend

```bash
cd frontend
npm run setup:deps:win  # Windows + Google Drive/OneDrive recomendado
npm run dev
```

En Windows, si el proyecto esta dentro de una carpeta sincronizada (por ejemplo Google Drive) o en una ruta con caracteres especiales, `npm install` puede corromper `node_modules`. El script `npm run setup:deps:win` instala las dependencias en `C:\temp\mi-asistente-frontend-deps`, y `npm run dev` / `npm run build` sincronizan el frontend a un runtime temporal en `C:\temp` para ejecutar Vite sin depender de `node_modules` dentro del workspace.

## URLs locales

| Servicio | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

## Firebase — Índice requerido

Crea un índice compuesto en Firestore:
- Colección: `conversations`
- Campo 1: `client_id` (Ascending)
- Campo 2: `updated_at` (Descending)

## Despliegue (Bonus)

Ver [Parte 7 de la guía del proyecto](./guiaproyectoagenteia.docx) para instrucciones de despliegue en Railway o Google Cloud Run.

## Despliegue en Railway

La forma más simple es crear 2 servicios en Railway dentro del mismo repositorio: uno para `backend/` y otro para `frontend/`.

### 1. Backend en Railway

- Crea un servicio nuevo desde este repositorio.
- Configura `Root Directory` = `backend`.
- Railway detectará [backend/Dockerfile](backend/Dockerfile).
- Variables recomendadas:
	- `PORT` = asignado por Railway
	- `OPENAI_API_KEY`
	- `TAVILY_API_KEY`
	- `FIREBASE_PROJECT_ID`
	- `FIREBASE_SERVICE_ACCOUNT_JSON` = contenido completo del JSON de service account en una sola variable segura
	- `CORS_ORIGINS` = URL pública del frontend en Railway, por ejemplo `https://mi-asistente-frontend.up.railway.app`

### 2. Frontend en Railway

- Crea un segundo servicio desde el mismo repositorio.
- Configura `Root Directory` = `frontend`.
- Railway usará [frontend/Dockerfile](frontend/Dockerfile).
- Variable requerida:
	- `VITE_API_BASE_URL` = URL pública del backend en Railway, por ejemplo `https://mi-asistente-backend.up.railway.app`

### 3. Comprobaciones finales

- Backend: `/health` debe responder `{"status":"ok"}`.
- Frontend: debe cargar clientes y poder abrir conversaciones sin depender del proxy local de Vite.
- Si el frontend no alcanza al backend, revisa que `CORS_ORIGINS` incluya exactamente la URL pública del frontend.
