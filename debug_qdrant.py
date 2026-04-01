import asyncio
from qdrant_client import QdrantClient
from app.config import get_settings

def check_qdrant():
    settings = get_settings()
    print(f"Connecting to Qdrant at: {settings.QDRANT_HOST}")
    
    if settings.qdrant_is_cloud:
        client = QdrantClient(
            url=settings.QDRANT_HOST,
            api_key=settings.QDRANT_API_KEY
        )
    else:
        client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        
    collection_name = settings.QDRANT_COLLECTION_NAME
    
    try:
        collections = client.get_collections().collections
        print(f"Available collections: {[c.name for c in collections]}")
        
        if collection_name not in [c.name for c in collections]:
            print(f"ERROR: Collection {collection_name} does not exist!")
            return

        count = client.count(collection_name=collection_name).count
        print(f"Total points in '{collection_name}': {count}")
        
        if count > 0:
            results, _ = client.scroll(
                collection_name=collection_name,
                limit=5,
                with_payload=True
            )
            for i, res in enumerate(results):
                print(f"\n--- Point {i} ---")
                print(f"ID: {res.id}")
                print(f"Payload Keys: {list(res.payload.keys())}")
                if 'collection' in res.payload:
                    print(f"Collection: {res.payload['collection']}")
                if 'access_roles' in res.payload:
                    print(f"Access Roles: {res.payload['access_roles']}")
                if 'source_document' in res.payload:
                    print(f"Document: {res.payload['source_document']}")
        else:
            print("Collection is empty. Indexing has not been performed or failed.")

    except Exception as e:
        print(f"Error checking Qdrant: {e}")

if __name__ == "__main__":
    check_qdrant()
