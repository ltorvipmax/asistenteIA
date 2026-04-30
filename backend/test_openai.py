import sys
sys.path.insert(0, '.')

from config import get_settings

settings = get_settings()
api_key = settings.openai_api_key

print("=" * 70)
print("VERIFICANDO ACCESO A OPENAI")
print("=" * 70)

# Test 1: Validar formato de la key
if api_key.startswith("sk-proj-"):
    print("✓ Formato de key válido (sk-proj-...)")
else:
    print("✗ Formato de key inválido")

# Test 2: Intentar conectar a OpenAI
try:
    from openai import OpenAI
    
    client = OpenAI(api_key=api_key)
    print("✓ Cliente OpenAI creado correctamente")
    
    # Test 3: Hacer una llamada a GPT-4o
    print("\nIntentando llamada a GPT-4o (timeout 30s)...")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hola, di solo 'OK'"}],
        max_tokens=5,
        timeout=30
    )
    
    print("\n✓✓✓ ¡ÉXITO! API KEY FUNCIONA")
    print(f"  Modelo: {response.model}")
    print(f"  Respuesta: {response.choices[0].message.content}")
    sys.exit(0)
    
except Exception as e:
    error_type = type(e).__name__
    error_msg = str(e)[:150]
    
    print(f"\n✗ ERROR: {error_type}")
    print(f"  Mensaje: {error_msg}")
    
    if "401" in error_msg or "authentication" in error_msg.lower() or "invalid_api_key" in error_msg:
        print("\n  → API KEY REVOCADA O INVÁLIDA")
        print("  → Solución: Genera una nueva key en https://platform.openai.com/api-keys")
    elif "timeout" in error_msg.lower():
        print("\n  → TIMEOUT: OpenAI no responde")
        print("  → Esto puede ser: problema de red, servidor caído o key bloqueada")
    elif "model" in error_msg.lower():
        print("\n  → GPT-4O NO DISPONIBLE para tu cuenta")
        print("  → Solución: Intenta con 'gpt-4' o espera acceso a GPT-4o")
    
    sys.exit(1)
