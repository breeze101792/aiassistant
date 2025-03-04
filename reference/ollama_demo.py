import ollama
from duckduckgo_search import DDGS

def web_search(query: str, num_results: int = 3) -> str:
    """
    Perform a web search and return formatted results
    """
    with DDGS() as ddgs:
        results = [r for r in ddgs.text(query, max_results=num_results)]
        return "\n".join([f"[{i+1}] {r['title']}: {r['body']}" for i, r in enumerate(results)])

def main():
    # Initialize chat with system message (agent configuration)
    messages = [{
        'role': 'system',
        'content': """You are a helpful AI assistant with web access. Follow these rules:
1. Use web search when you need current information
2. Be concise and factual
3. When using search results, cite sources using [number] notation
4. If unsure, say you don't know"""
    }]

    while True:
        # Get user input
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit']:
                break

            # Check if user is forcing a web search
            if user_input.startswith('!web'):
                query = user_input[4:].strip()
                search_results = web_search(query)
                messages.append({'role': 'user', 'content': f"Search results for '{query}':\n{search_results}"})
                print(f"\nPerformed web search: {query}")
                continue

            # Add user message to context
            messages.append({'role': 'user', 'content': user_input})

            # Generate response
            response = ollama.chat(
                # model='mistral',  # Change to your preferred model
                model='deepseek-r1:latest',  # Change to your preferred model
                messages=messages,
                options={'temperature': 0.7}
            )
            assistant_message = response['message']['content']
            
            # Display and store response
            print(f"\nAssistant: {assistant_message}")
            messages.append({'role': 'assistant', 'content': assistant_message})

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {str(e)}")
            continue

if __name__ == "__main__":
    print("Starting AI agent. Type 'exit' to quit or '!web <query>' to force a web search")
    main()
