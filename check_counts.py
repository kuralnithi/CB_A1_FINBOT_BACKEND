import asyncio
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from app.config import get_settings

def check_counts():
    settings = get_settings()
    client = QdrantClient(url=settings.QDRANT_HOST, api_key=settings.QDRANT_API_KEY)
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    print(f"Collection: {collection_name}")
    
    total = client.count(collection_name=collection_name).count
    print(f"Total: {total}")
    
    for coll in ["finance", "engineering", "marketing", "general"]:
        cnt = client.count(
            collection_name=collection_name,
            count_filter=Filter(must=[FieldCondition(key="collection", match=MatchValue(value=coll))])
        ).count
        print(f" - {coll}: {cnt}")

if __name__ == "__main__":
    check_counts()
