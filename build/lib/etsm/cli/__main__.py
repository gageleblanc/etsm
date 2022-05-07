from pathlib import Path
from etsm.managers import ServerManager, SourcesManager
from clilib.builders.app import EasyCLI
from clilib.util.logging import Logging
from clilib.config.config_loader import JSONConfigurationFile
import os


class ETSMCLI:
    """
    Enemy Territory Server Manager CLI
    """
    _root = None
    def __init__(self, debug: bool = False):
        """
        :param debug: Enable debug mode
        """
        self.debug = debug
        ETSMCLI._root = self

    class Sources:
        """
        Sources for CLI
        """
        def __init__(self, debug: bool = False, sources_url: str = None):
            """
            :param debug: Enable debug mode
            :param sources_url: URL for sources
            """
            self.debug = debug
            self.sources_url = sources_url

        def update(self, all_versions: bool = False):
            """
            Update sources
            """
            sources_manager = SourcesManager(debug=self.debug, sources_url=self.sources_url)
            sources_manager.download_sources(all_versions=all_versions)

    class Config:
        """
        Configuration for the CLI
        """
        def __init__(self, debug: bool = False):
            """
            :param debug: Enable debug mode
            """
            self.config_path = Path.home() / ".etsm" / "config"
            self.config = JSONConfigurationFile(self.config_path, schema={"default_server": str}, auto_create={"default_server": "default"})
            self.logger = Logging("etsm", "config", debug=debug).get_logger()

        def get(self, config_key: str):
            """
            Get a configuration value
            :param config_key: Configuration key
            :return: Configuration value
            """
            value = self.config[config_key]
            if value:
                print(value)
            else:
                self.logger.error("Configuration key {} does not exist.".format(config_key))
        
        def set(self, config_key: str, config_value: str):
            """
            Set a configuration value
            :param config_key: Configuration key
            :param config_value: Configuration value
            """
            self.config[config_key] = config_value
            self.config.write()

    class Server:
        """
        Server manager
        :alias servers:
        """
        def __init__(self, debug: bool = False, server_name: str = None):
            """
            :param debug: Enable debug mode
            :param server_name: Server to manage (default: config setting)
            """
            if server_name is None:
                c = ETSMCLI._root.Config(debug=debug)
                server_name = c.config["default_server"]
            self.server_name = server_name
            self.debug = debug
        
        def run(self):
            """
            Run Enemy Territory server
            """
            manager = ServerManager(self.server_name, debug=self.debug)
            manager.run_server()

        def list(self):
            """
            List all servers
            """
            servers = os.listdir("/var/lib/etsm/servers")
            if len(servers) == 0:
                print("No servers found.")
            for server in servers:
                print(server)

        def create(self, version: str = None, force: bool = False):
            """
            Create a server
            :param version: Server version (default: latest)
            :param force: Force creation (delete and recreate, default: False)
            """
            manager = ServerManager(self.server_name, debug=self.debug)
            if manager.server_path.joinpath("etmain").exists():
                if not force:
                    print("Server already exists! Use --force to force creation.")
                    return
            self.update(version, force=force)

        def update(self, version: str, force: bool = False):
            """
            Update a server
            :param version: Version to update to
            :param force: Force update if you are already on the latest version (default: False)
            """
            manager = ServerManager(self.server_name, debug=self.debug)
            manager.update_server(version, force=force)

        def link_service(self):
            """
            Link systemd service file to systemd directory
            """
            manager = ServerManager(self.server_name, debug=self.debug)
            manager.link_systemd_file()
            manager.reload_systemd()

        class Mod:
            """
            :alias mods:
            Server mod manager
            """
            def __init__(self, debug: bool = False, server_name: str = None):
                """
                :param debug: Enable debug mode
                :param server_name: Server to manage (default: config setting)
                """
                if server_name is None:
                    c = ETSMCLI._root.Config(debug=debug)
                    server_name = c.config["default_server"]
                self.server_name = server_name
                self.debug = debug

            def set(self, mod_name: str):
                """
                Set server mod
                :param mod_name: Mod to set for fs_game
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.set_mod(mod_name)

            def list(self):
                """
                List all installable mods
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.list_mods()
                if len(res) == 0:
                    print("No mods found.")
                for mod in res:
                    print(mod)

            def install(self, mod_name: str, mod_version: str = None, force: bool = False):
                """
                Install a mod
                :param mod_name: Mod to install
                :param mod_version: Mod version (default: latest)
                :param force: Force installation (delete and recreate, default: False)
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.install_mod(mod_name, mod_version, force=force)


        class Config:
            """
            Server config manager
            """
            def __init__(self, debug: bool = False, server_name: str = None):
                """
                :param debug: Enable debug mode
                :param server_name: Server to manage (default: config setting)
                """
                if server_name is None:
                    c = ETSMCLI._root.Config(debug=debug)
                    server_name = c.config["default_server"]
                self.server_name = server_name
                self.debug = debug

            def add_startup_config(self, config_name: str):
                """
                :alias asc:
                Add a startup config
                :param config_name: Config to add
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.add_startup_config(config_name)

            def remove_startup_config(self, config_name: str):
                """
                :alias rsc:
                Remove a startup config
                :param config_name: Config to remove
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.remove_startup_config(config_name)

            def create(self, config_name: str, from_template: str = None, activate: bool = False):
                """
                Create a config
                :param config_name: Config name
                :param from_template: Template to use (default: None)
                :param activate: Activate config (default: False)
                """
                cvars = None
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.create_config(config_name=config_name, from_template=from_template, cvars=cvars, activate=activate)

            def list(self):
                """
                List all config files
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.list_configs()
                if res is not None:
                    for config in res:
                        print(config)

            def list_cvars(self, config_name: str):
                """
                List all config cvars
                :param config: Config to list cvars for
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.list_cvars(config_name)
                if res is not None:
                    for cvar in res:
                        print(cvar)

            def list_execs(self, config_name: str):
                """
                List all exec commands in a config
                :param config: Config to list execs for
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.list_execs(config_name)
                if res is not None:
                    for exec in res:
                        print(exec)

            def list_templates(self):
                """
                List all config templates
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.list_templates()
                if res is not None:
                    for template in res:
                        print(template)

            def activate(self, config_name: str):
                """
                Activate a config
                :param config_name: Config to activate
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.activate_config(config_name)

            def deactivate(self, config_name: str):
                """
                Deactivate a config
                :param config_name: Config to deactivate
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.deactivate_config(config_name)

            def get(self, config_name: str, cvar: str):
                """
                Get a server config value
                :param config_name: Config to search for the cvar in
                :param cvar: CVar to get
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                res = manager.get_cvar(config_name, cvar)
                if res is not None:
                    print(res)

            def set(self, config_name: str, cvar: str, value: str):
                """
                Update a server config value
                :param config_name: Config file to update
                :param cvar: CVar to update
                :param value: Value to update to
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.update_cvars(config_name, {cvar: value})
            
            def exec(self, config_name: str, exec_name: str):
                """
                Add an exec command to a config
                :param config_name: Config to add the exec to
                :param exec_name: Config to exec
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.add_exec(config_name, exec_name)

            def remove_exec(self, config_name: str, exec_name: str):
                """
                :alias rme:
                Remove an exec command from a config
                :param config_name: Config to remove the exec from
                :param exec_name: Config to remove
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.remove_exec(config_name, exec_name)

            def set_ip(self, ip: str):
                """
                Set the server IP
                :param ip: IP to set
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.set_ip(ip)
            
            def set_port(self, port: int):
                """
                Set the server port
                :param port: Port to set
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.set_port(port)

            def set_mod(self, mod_name: str):
                """
                Set the server mod
                :param mod_name: Mod to run
                """
                manager = ServerManager(self.server_name, debug=self.debug)
                manager.set_mod(mod_name)


def cli():
    """
    CLI entry point
    """
    EasyCLI(ETSMCLI, enable_logging=True, debug=True)