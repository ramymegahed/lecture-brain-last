import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Single shared async OpenAI client — initialized once at import time.
# All modules must import from here instead of instantiating their own client.
# This avoids repeated connection pool setup on every API call.
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
