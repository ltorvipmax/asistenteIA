import sys
import socket
sys.path.insert(0, '.')

from config import get_settings

settings = get_settings()
api_key = settings.openai_api_key

print("=" * 70)
print("VERIFICANDO API KEY DE OPENAI")
print("=" * 70)
print()

# Test básico sin llamar a OpenAI
if not api_key:
    print("✗ NO HAY API KEY CONFIGURADA")
    sys.exit(1)

if not api_key.startswith("sk-proj-"):
    print("✗ FORMATO INVÁLIDO. Key debe empezar con 'sk-proj-'")
    sys.exit(1)

print(f"✓ Formato válido: {api_key[:30]}...")
print()
print("Para verificar si la key funciona REALMENTE:")
print()
print("  Opción 1: Ir a https://platform.openai.com/api-keys")
print("            y verificar que la key esté ACTIVA (verde)")
print()
print("  Opción 2: Hacer test por terminal:")
print()
print(f'    curl -X POST "https://api.openai.com/v1/chat/completions"')
print(f'      -H "Authorization: Bearer {api_key[:20]}..."')
print(f'      -H "Content-Type: application/json"')
print(f'      -d \'{{"model":"gpt-4o","messages":[{{"role":"user","content":"Hi"}}]}}\'')
print()

# Intentar conectar a OpenAI con timeout corto
print("Intentando conexión rápida a OpenAI...")
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex(('api.openai.com', 443))
    sock.close()
    
    if result == 0:
        print("✓ Conexión de red a api.openai.com: OK")
    else:
        print("✗ No se puede conectar a api.openai.com (firewall o DNS?)")
except Exception as e:
    print(f"⚠ Error en conexión de red: {e}")
