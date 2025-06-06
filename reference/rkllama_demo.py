import requests
import json
import sys
import os
import configparser

CONFIG_FILE = os.path.expanduser("~/RKLLAMA/rkllama.ini")
STREAM_MODE = True
VERBOSE = False
HISTORY = []
PREFIX_MESSAGE = "<|im_start|>system You are a helpful assistant. <|im_end|> <|im_start|>user"
SUFFIX_MESSAGE = "<|im_end|><|im_start|>assistant"

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


if not os.path.exists(CONFIG_FILE):
    print("Configuration file not found. Creating with default values...")
    config = configparser.ConfigParser()
    config["server"] = {"port": "8080"}
    with open(CONFIG_FILE, "w") as configfile:
        config.write(configfile)

config = configparser.ConfigParser()
config.read(CONFIG_FILE)


PORT = config["server"].get("port", "8080")
API_URL = f"http://127.0.0.1:{PORT}/"
MODEL = "Qwen2.5-3B-Instruct-rk3588-w8a8_g256-opt-1-hybrid-ratio-1.0"

# Check status of rkllama API
def check_status():
    try:
        response = requests.get(API_URL)
        return response.status_code
    except:
        return 500
# Function to change model if the old model loaded is not the same one to execute
def switch_model(new_model):
    response = requests.get(API_URL + "current_model")
    if response.status_code == 200:
        current_model = response.json().get("model_name")

        if current_model:
            print(f"{YELLOW}Unloading the current model: {current_model}{RESET}")
            unload_model()

    if not load_model(new_model):
        print(f"{RED}Unable to load model {new_model}.{RESET}")
        return False

    return True
# Loads a specific template on the server.
def load_model(model_name, From=None, huggingface_path=None):

    if From != None and huggingface_path != None:
        payload = {"model_name": model_name, "huggingface_path": huggingface_path, "from": From}
    else:
        payload = {"model_name": model_name}

    try:
        response = requests.post(API_URL + "load_model", json=payload)
        if response.status_code == 200:
            print(f"{GREEN}{BOLD}Model {model_name} loaded successfully.{RESET}")
            return True
        else:
            print(f"{RED}Error loading model: {response.status_code} - {response.json().get('error', response.text)}{RESET}")
        return False
    except requests.RequestException as e:
        print(f"{RED}Query error: {e}{RESET}")
        return False


# Unloads the currently loaded model.
def unload_model():
    try:
        response = requests.post(API_URL + "unload_model")
        if response.status_code == 200:
            print(f"{GREEN}{BOLD}Model successfully unloaded.{RESET}")
        else:
            print(f"{RED}Error when unloading model: {response.status_code} - {response.json().get('error', response.text)}{RESET}")
    except requests.RequestException as e:
        print(f"{RED}Query error: {e}{RESET}")

# Sends a message to the loaded model and displays the response.
def send_message(message):
    global HISTORY

    HISTORY.append({"role": "user", "content": message})

    # if VERBOSE == True:
    #     print(HISTORY)

    payload = {
        "messages": HISTORY,
        "stream": STREAM_MODE
    }


    try:
        if STREAM_MODE:
            with requests.post(API_URL + "generate", json=payload, stream=True) as response:
                
                if response.status_code == 200:
                    print(f"{CYAN}{BOLD}Assistant:{RESET} ", end="")
                    assistant_message = ""
                    final_json        = {
                        "usage": {
                            "tokens_per_second": 0,
                            "completion_tokens": 0
                        }
                    }

                    for line in response.iter_lines(decode_unicode=True):
                        if line:
                            try:
                                response_json = json.loads(line)
                                final_json = response_json

                                content_chunk = response_json["choices"][0]["content"]
                                sys.stdout.write(content_chunk)
                                sys.stdout.flush()
                                assistant_message += content_chunk
                            except json.JSONDecodeError:
                                print(f"{RED}Error detecting JSON response.{RESET}")

                    if VERBOSE == True:
                        tokens_per_second = final_json["usage"]["tokens_per_second"]
                        completion_tokens = final_json["usage"]["completion_tokens"]
                        print(f"\n\n{GREEN}Tokens per second{RESET}: {tokens_per_second}")
                        print(f"{GREEN}Number of tokens  {RESET}: {completion_tokens}")

                    HISTORY.append({"role": "assistant", "content": assistant_message})

                    # Return to line after last token
                    print("\n")

                else:
                    print(f"{RED}Streaming error: {response.status_code} - {response.text}{RESET}")

        else:
            response = requests.post(API_URL + "generate", json=payload)
            if response.status_code == 200:
                response_json = response.json()
                assistant_message = response_json["choices"][0]["content"]

                print(f"{CYAN}{BOLD}Assistant:{RESET} {assistant_message}")

                if VERBOSE == True:
                        tokens_per_second = final_json["usage"]["tokens_per_second"]
                        completion_tokens = final_json["usage"]["completion_tokens"]
                        print(f"\n\n{GREEN}Tokens per second{RESET}: {tokens_per_second}")
                        print(f"{GREEN}Number of Tokens  {RESET}: {completion_tokens}")
                        
                HISTORY.append({"role": "assistant", "content": assistant_message})
            else:
                print(f"{RED}Query error: {response.status_code} - {response.text}{RESET}")

    except requests.RequestException as e:
        print(f"{RED}Query error: {e}{RESET}")
# Interactive function for chatting with the model.
def chat():
    global VERBOSE, STREAM_MODE, HISTORY, PREFIX_MESSAGE
    os.system("clear")
    # print_help_chat()
    
    while True:
        user_input = input(f"{CYAN}You:{RESET} ")

        if user_input == "/help":
            print_help_chat()
        elif user_input == "/clear":
            HISTORY = []
            print(f"{GREEN}Conversation history successfully reset{RESET}")
        elif user_input == "/cls" or user_input == "/c":
            os.system("clear")
        elif user_input.lower() == "exit":
            print(f"{RED}End of conversation.{RESET}")
            break
        elif user_input == "/set stream":
            STREAM_MODE = True
            print(f"{GREEN}Stream mode successfully activated!{RESET}")
        elif user_input == "/unset stream":
            STREAM_MODE = False
            print(f"{RED}Stream mode successfully deactivated!{RESET}")
        elif user_input == "/set verbose":
            VERBOSE = True
            print(f"{GREEN}Verbose mode successfully activated!{RESET}")
        elif user_input == "/unset verbose":
            VERBOSE = False
            print(f"{RED}Verbose mode successfully deactivated!{RESET}")
        elif user_input == "/set system":
            system_prompt = input(f"{CYAN}System prompt: {RESET}")
            PREFIX_MESSAGE = f"<|im_start|>{system_prompt}<|im_end|> <|im_start|>user"
            print(f"{GREEN}System message successfully modified!")
        else:
            # If content is not a command, then send content to template
            send_message(user_input)
def main():
    global PORT

    # use_no_conda = "--no-conda" in sys.argv
    # sys.argv = [arg for arg in sys.argv if arg != "--no-conda"]

    # Check minimum number of entries
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1]

    if check_status() != 200 and command not in ['serve', 'update']:
        print(f"{RED}Error: Server not started!\n{RESET}rkllama serve{CYAN} command to start the server.{RESET}")
        sys.exit(0)

    # Start of condition sequence
    if command == "help":
        # print_help()
        print(f"{RED}No help for that.{RESET}")

    # elif command == "serve":
    #
    #     if len(sys.argv) > 2:
    #         PORT = sys.argv[2]
    #
    #     os.system(f"bash ~/RKLLAMA/server.sh {"--no-conda" if use_no_conda else ""} --port={PORT}")

    # elif command == "update":
    #     update()
    #
    # elif command =="list":
    #     list_models()
    #
    # elif command == "load_model":
    #     if len(sys.argv) < 3:
    #         print(f"{RED}Error: You must specify the model name.{RESET}")
    #     else:
    #         load_model(sys.argv[2])
    #
    # elif command == "unload":
    #     unload_model()

    elif command == "run":
        if len(sys.argv) == 3:
            if not switch_model(sys.argv[2]):
                return
        elif len(sys.argv) >= 4:
            load_model(sys.argv[2], sys.argv[3], sys.argv[4])

        chat()
            
    # elif command == "rm":
    #     if sys.argv[2] is None:
    #         print(f"{RED}Error: You must specify the model name.{RESET}")
    #     else:
    #         remove_model(sys.argv[2])
    #
    # elif command == "pull":
    #     pull_model(sys.argv[2] if len(sys.argv) < 2 else "" )
    
    else:
        print(f"{RED}Unknown command: {command}.{RESET}")
        # print_help()


# Launching the main function: program start
if __name__ == "__main__":
    main()
