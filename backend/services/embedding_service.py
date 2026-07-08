"""
Embedding service using Google Gemini gemini-embedding-001 model.

Generates 3072-dimension vector embeddings for text retrieval.
"""
import os
from google import genai
from google.genai import types

# Initialize Gemini client for embeddings only
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable is missing!")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def get_embedding(text: str) -> list[float]:
    """
    Generate embedding vector for text using Gemini gemini-embedding-001.
    
    Args:
        text: Input text to embed
        
    Returns:
        List of 3072 floats representing the embedding vector
        
    Raises:
        Exception: If client is not initialized or API call fails
    """
    if not client:
        raise Exception("Gemini client not initialized - check GEMINI_API_KEY")
        
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY"  # Optimized for search use case
        )
    )
    return response.embeddings[0].values
