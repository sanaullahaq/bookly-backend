"""Book Information Retrieval Agent -- CLI.

Fetch structured book details by title, using Google Books, Open Library,
and (as a last resort) Tavily web search.

Usage:
    python agent.py "The indispensable Calvin and Hobbes"
"""

from dotenv import load_dotenv
from langchain.agents import create_agent

from src.books.schemas import BookInfo

load_dotenv()


from src.books.agent.system_prompt import SYSTEM_PROMPT
from src.books.agent.tools import (
    search_book,
    search_book_openlibrary,
    search_book_tavily,
)

agent = create_agent(
    model="google_genai:gemini-3.5-flash-lite",
    tools=[search_book, search_book_openlibrary, search_book_tavily],
    system_prompt=SYSTEM_PROMPT,
    response_format=BookInfo,
)
