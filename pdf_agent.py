import os

import google.generativeai as genai
from duckduckgo_search import DDGS
from dotenv import load_dotenv

# Load variables from a local .env file if present.
load_dotenv()

# Option 1: Put GEMINI_API_KEY in a .env file.
# Option 2: Set it in your shell/environment:
# PowerShell (current session): $env:GEMINI_API_KEY="your_key_here"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "PASTE_YOUR_GEMINI_API_KEY_HERE")

# Configure Gemini client and initialize the requested model.
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Initialize DuckDuckGo search client.
ddg_client = DDGS()


def pdf_hunter_agent(user_request):
    """Find likely PDF links by rewriting query with Gemini and searching DuckDuckGo."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        print("WARNING: Gemini API key is not set.")
        print("Please paste your key into GEMINI_API_KEY before running searches.")
        return []

    # Step 1: Ask Gemini to rewrite into an optimized search query.
    prompt = (
        "You are an expert search query optimizer.\n"
        "Rewrite the user's request into one concise, high-quality web search query.\n"
        "You MUST append 'filetype:pdf' to the end of the query.\n"
        "Output only the final query text, with no extra words, no quotes, and no markdown.\n\n"
        f"User request: {user_request}"
    )

    response = model.generate_content(prompt)
    optimized_query = (response.text or "").strip().strip('"').strip("'")
    if not optimized_query.lower().endswith("filetype:pdf"):
        optimized_query = f"{optimized_query} filetype:pdf".strip()

    # Step 2: Search web using DuckDuckGo with up to 5 results.
    with DDGS() as search_client:
        results = list(search_client.text(optimized_query, max_results=5))

    # Step 3: Print only result entries that look like direct PDF links.
    pdf_results = []
    print("\n" + "=" * 60)
    print("PDF Hunter Results")
    print("=" * 60)
    print(f"Optimized Query: {optimized_query}\n")

    for item in results:
        url = str(item.get("href", "")).strip()
        title = str(item.get("title", "Untitled")).strip()
        if ".pdf" in url.lower():
            pdf_results.append({"title": title, "url": url})
            print(f"Title         : {title}")
            print(f"Download Link : {url}")
            print("-" * 60)

    if not pdf_results:
        print("WARNING: No direct PDF links were found in the top 5 results.")
        print("-" * 60)

    return pdf_results


if __name__ == "__main__":
    if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        print("WARNING: GEMINI_API_KEY is still the placeholder.")
        print("Set GEMINI_API_KEY in a .env file or environment variable.\n")

    print("Running PDF Hunter agent tests...\n")

    pdf_hunter_agent('Theodore Levitt "Marketing Myopia" Harvard Business Review 1960')
    pdf_hunter_agent("Alexander Chernev Strategic Marketing Management textbook full")
