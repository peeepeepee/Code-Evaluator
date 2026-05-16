import os
import json
import logging
import re
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional, Union
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LLM Configuration
LLM_API_URL = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4000"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))

logger = logging.getLogger(__name__)

async def query_llm(
    prompt: str, 
    model: str = DEFAULT_MODEL,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
    retry_count: int = 2
) -> str:
    """
    Query the LLM API
    
    Args:
        prompt: The prompt to send to the LLM
        model: The model to use
        temperature: Temperature parameter for generation
        max_tokens: Maximum tokens to generate
        retry_count: Number of retry attempts
        
    Returns:
        The LLM response text
    """
    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY environment variable is not set")
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    for attempt in range(retry_count + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    LLM_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"LLM API error: {response.status} - {error_text}")
                        
                        # If this is the last attempt and we're using the primary model, try backup
                        if attempt == retry_count and model == DEFAULT_MODEL:
                            logger.info(f"Trying backup model {BACKUP_MODEL}")
                            return await query_llm(
                                prompt, 
                                model=BACKUP_MODEL,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                retry_count=1
                            )
                            
                        # If this is the last attempt, raise the error
                        if attempt == retry_count:
                            response.raise_for_status()
                        
                        # Wait before retrying
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                    
        except Exception as e:
            logger.error(f"Error querying LLM: {str(e)}", exc_info=True)
            
            if attempt == retry_count:
                if model == DEFAULT_MODEL:
                    logger.info(f"Trying backup model {BACKUP_MODEL}")
                    return await query_llm(
                        prompt, 
                        model=BACKUP_MODEL,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        retry_count=1
                    )
                else:
                    raise
            
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    # If we somehow get here, raise an error
    raise RuntimeError("Failed to query LLM after multiple attempts")

async def query_multiple_llms(
    prompt: str,
    models: List[str],
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS
) -> List[str]:
    """
    Query multiple LLM models with the same prompt
    
    Args:
        prompt: The prompt to send
        models: List of models to query
        temperature: Temperature parameter for generation
        max_tokens: Maximum tokens to generate
        
    Returns:
        List of responses from each model
    """
    tasks = [
        query_llm(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
        for model in models
    ]
    
    return await asyncio.gather(*tasks, return_exceptions=True)