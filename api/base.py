# import re

# datetime
from datetime import datetime
from tzlocal import get_localzone

# Websearch
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import random

class BaseAPI:
    NAME = ""
    DESCRIPTION = ""
    PARAMETERS = {}
    def execute(self, **kwargs):
        raise NotImplementedError("You must implement the execute method.")

# from .base import BaseAPI
class WeatherAPI(BaseAPI):
    NAME = "WeatherAPI"
    DESCRIPTION = "Get weather information for a specific location."
    PARAMETERS = {
            "location": "string – Name of the city or area."
        }
    def execute(self, location="Taipei"):
        return f"The weather in {location} is sunny and 25°C."

class CurrentDateTimeAPI(BaseAPI):
    NAME = "CurrentDateTimeAPI"
    DESCRIPTION = "Get current date/time/zone information in the real word."
    PARAMETERS = {}
    def execute(self):

        # Get the system's local timezone
        local_timezone = get_localzone()

        # Get current time with system's timezone
        local_time = datetime.now(local_timezone)

        respone = f"Local Time with Timezone:{local_time}"
        return respone

class WebSearchAPI(BaseAPI):
    NAME = "WebSearchAPI"
    DESCRIPTION = "Search online with query, to get the latest/realtime informations."
    PARAMETERS = {
            "query": "string – Things you want to search online."
        }
    # Function to get page content and filter it
    def get_filtered_content(self, url, keyword=None):
        # # List of User-Agent strings to rotate
        # user_agents = [
        #     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        #     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/118.0.0.0 Safari/537.36",
        #     "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36"
        # ]
        # # Randomly select a User-Agent
        # headers = {"User-Agent": random.choice(user_agents)}

        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0'}

        # Optional: Set up a proxy
        # proxies = {
        #     "http": "http://your_proxy_ip:port",
        #     "https": "http://your_proxy_ip:port"
        # }

        # url = "https://www.example.com"

        # Send request with headers and proxies
        # response = requests.get(url, headers=headers, proxies=proxies)

        try:
            # Get the HTML content from the URL
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise an error if the request fails

            # Parse the content with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Get only the main content (based on <p> tags or article body)
            paragraphs = soup.find_all('p')
            content = " ".join([p.get_text() for p in paragraphs])

            # Optional: Filter content if a keyword is specified
            if keyword and keyword.lower() in content.lower():
                return content
            elif not keyword:
                return content
            else:
                return None  # Skip content if keyword not found
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    def execute(self, query):
        max_result = 10
        # Perform a DuckDuckGo search
        # query = "Python web scraping tutorial"
        search_result = ""
        result_cnt = 0
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_result * 2)
            for result in results:
                content = self.get_filtered_content(result['href'])
                if content is not None:
                    search_result+=f"Title: {result['title']}\n"
                    search_result+=f"Link: {result['href']}\n"
                    # Get and filter page content
                    search_result+=f"Content: {content}\n"
                    result_cnt += 1
                    if result_cnt >= max_result:
                        break


        return search_result


if __name__ == "__main__":
    # input_text = '[WeatherAPI(location="Taipei")]'
    # result = parse_ai_message(input_text)
    # print("Result:", result)

    api = WebSearchAPI()
    result = api.execute('what is google.')
    print("Result:", result)

