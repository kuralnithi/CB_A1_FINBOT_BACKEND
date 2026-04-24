import os
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

# Load env in case OLLAMA_BASE_URL is set there
load_dotenv()

def test_ollama():
    try:
        print("Testing Ollama connection...")
        llm = ChatOllama(
            model="llama3.1:8b",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.7
        )
        
        response = llm.invoke("Say 'Ollama is alive!' if you can hear me.")
        print("-" * 30)
        print(f"Ollama response: {response.content}")
        print("-" * 30)
        print("Success! Ollama is correctly configured and the model is loaded.")
        
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        print("Make sure Ollama is running (`ollama serve`) and 'llama3.1:8b' is pulled.")

if __name__ == "__main__":
    test_ollama()
