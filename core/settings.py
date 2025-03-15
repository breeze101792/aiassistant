# list all settings here
class Setting:
    class Info:
        Version='0.1'
        Debug=False
    class Message:
        Exit='Bye'

    # Method for settings
    ################################################################
    @staticmethod
    def saveConfig(config, filename = 'config.ini'):
        Setting.dumpConfig(config)

        for each_cag in config:
            for each_config in config[each_cag]:
                dbg_debug(each_cag, ": ", each_config)

        with open(filename, 'w') as configfile:
            config.write(configfile)

    @staticmethod
    def dumpConfig(config):
        config['Info']['Debug'] = Setting.Info.Debug
        config['Info']['Version'] = Setting.Info.Version.__str__()
    @staticmethod
    def createConfig(config):
        config.add_section('Info')
        config['Info']['Debug'] = Setting.Info.Debug
        config['Info']['Version'] = Setting.Info.Version.__str__()

    @staticmethod
    def readConfig(config, filename = 'config.ini'):
        Setting.createConfig(config)
        if os.path.isfile(filename):
            try:
                config.read(filename)
            except:
                pass
        Setting.Info.Debug = config['Info']['Debug']
        Setting.Info.Version = int(config['Info']['Version'])
