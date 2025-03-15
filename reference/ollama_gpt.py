#!/bin/env python3
import ollama
import requests
import json

def search_web(query):
    """Search the web using SerpAPI or another search engine API."""
    api_key = "your_serpapi_key"  # 替換為你的 SerpAPI API 金鑰
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": api_key,
        "num": 3,  # 限制結果數量
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        results = response.json().get("organic_results", [])
        return "\n".join([f"{r['title']}: {r['link']}" for r in results])
    return "No results found."

def chat_with_ollama(prompt):
    """Interact with Ollama and determine if web search is needed."""
    system_prompt = "If the question requires real-time or updated information, respond with 'SEARCH NEEDED'. Otherwise, answer normally."
    response = ollama.chat(
        # model="mistral",  # 你可以替換為適合的模型
        # model='qwen2.5:1.5b',  # Change to your preferred model
        model='deepseek-r1:latest',  # Change to your preferred model
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    )
    answer = response["message"]["content"]
    print("Answser: " + answer.__str__())
    
    if "SEARCH NEEDED" in answer:
        search_results = search_web(prompt)
        return f"(Web Search Results)\n{search_results}"
    
    return answer

if __name__ == "__main__":
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        response = chat_with_ollama(user_input)
        print(f"AI: {response}\n")

