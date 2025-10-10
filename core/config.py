from utility.config import *

class AIAppConfig(AppConfig):
    # Read only variable
    config_file = "./config.json"
    log_level = "Information"
    def __init__(self):
        _args = {}
    class about:
        program_name = 'AI Assistant'
        version='0.1.0'

class AIConfigManager(ConfigManager):
    config = None
    def __init__(self):
        self.config = AIAppConfig
