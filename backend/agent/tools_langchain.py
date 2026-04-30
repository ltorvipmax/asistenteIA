from langchain_core.tools import tool
from tools.tavily_search import search_content


@tool
async def search_real_time_info(query: str) -> str:
    """
    Busca información actualizada sobre el mercado inmobiliario para asesorar clientes.

    Usa esta herramienta cuando el usuario solicite datos externos que cambian en el tiempo,
    por ejemplo:
    - Precio promedio por m2 en distritos como Miraflores, San Isidro, Barranco, Surco o La Molina.
    - Tendencias del mercado inmobiliario (subidas, caídas, oferta y demanda).
    - Comparativas de zonas para compra, alquiler o inversión.
    - Tasas hipotecarias vigentes y condiciones de financiamiento en Perú.
    - Normativa reciente de alquiler, compra-venta o zonificación urbana.
    - Noticias inmobiliarias que impacten decisiones de compra o inversión.
    - Información de servicios cercanos (colegios, transporte, bancos, comercio) por zona.

    No usar esta herramienta para responder con datos ya presentes en el perfil del cliente
    (presupuesto, tipo de propiedad, historial o preferencias), salvo que se necesite
    complementar con contexto actualizado de mercado.

    Args:
        query: Consulta de búsqueda en lenguaje natural. Incluye zona, tipo de propiedad
               y objetivo del cliente para mejorar precisión.

    Returns:
        Texto formateado con resultados, extracto y fuente web.
    """
    results = await search_content(query)
    if not results:
        return "No se encontraron resultados para esa búsqueda."
    formatted = [
        f"**{r['title']}**\n{r['content']}\nFuente: {r['url']}"
        for r in results
    ]
    return "\n\n---\n\n".join(formatted)
