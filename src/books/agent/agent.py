"""Book Information Retrieval Agent -- CLI.

Fetch structured book details by title, using Google Books, Open Library,
and (as a last resort) Tavily web search.

Usage:
    python agent.py "The indispensable Calvin and Hobbes"
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from src.books.agent.system_prompt import SYSTEM_PROMPT
from src.books.agent.tools import (
    search_book,
    search_book_openlibrary,
    search_book_tavily,
)
from src.books.schemas import BookInfo
from src.config import Config

model = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite", api_key=Config.GOOGLE_API_KEY
)

agent = create_agent(
    model=model,
    tools=[search_book, search_book_openlibrary, search_book_tavily],
    system_prompt=SYSTEM_PROMPT,
    response_format=BookInfo,
)
