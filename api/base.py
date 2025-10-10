# datetime
from datetime import datetime
from tzlocal import get_localzone

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

        respone = f"Current system local datetime :{local_time}"
        return respone

if __name__ == "__main__":
    # input_text = '[WeatherAPI(location="Taipei")]'
    # result = parse_ai_message(input_text)
    # print("Result:", result)

    api = WebSearchAPI()
    result = api.execute('what is google.')
    print("Result:", result)

