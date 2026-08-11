from fastapi import FastAPI
from pydantic import BaseModel
import urllib.request
from bs4 import BeautifulSoup

app = FastAPI(title="AI Multitask Routing API")

class UserInput(BaseModel):
    message: str

def core_engine(user_input):
    text_lower = user_input.lower()
    if "calculate" in text_lower or "math" in text_lower:
        numbers = [int(s) for s in text_lower.split() if s.isdigit()]
        if len(numbers) >= 2: return f"Math: {numbers} + {numbers} = {numbers + numbers}"
        return "Provide two numbers."
    elif "read" in text_lower or "http" in text_lower:
        words = text_lower.split()
        url = next((w for w in words if w.startswith("http")), None)
        if not url: return "Missing URL."
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla'})
            html = urllib.request.urlopen(req).read()
            page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
            return f"Scraped Data: {page_text[:100]}..."
        except Exception as e: return f"Error: {str(e)}"
    return f"Processed general message: {user_input}"

@app.post("/api/v1/agent")
def process_agent_request(data: UserInput):
    ai_output = core_engine(data.message)
    return {"status": "success", "result": ai_output}
