from elasticsearch import AsyncElasticsearch
from models.schemas import Competitor
import os


async def search_competitors(company_description: str, es: AsyncElasticsearch) -> list[dict]:
    """Search Elastic for companies competing in the same space."""
    resp = await es.search(
        index="companies",
        query={
            "multi_match": {
                "query": company_description,
                "fields": ["description", "positioning", "category"],
            }
        },
        size=10,
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]


async def index_company(company_data: dict, es: AsyncElasticsearch) -> None:
    """Index a company into Elastic for future searches."""
    await es.index(index="companies", document=company_data)
