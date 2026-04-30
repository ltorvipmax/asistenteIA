from tavily import AsyncTavilyClient
from config import get_settings


async def search_content(query: str, max_results: int = 5) -> list[dict]:
    """
    Busca información actualizada usando Tavily.
    Adapta la query base al dominio de tu asistente.
    """
    settings = get_settings()
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    response = await client.search(
        query=query,
        max_results=max_results,
        search_depth="basic",
        include_answer=False,
    )
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0.0)
        }
        for r in response.get("results", [])
    ]
