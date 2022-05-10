from string import Template
import subprocess
import datetime
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile
from clilib.util.logging import Logging
from clilib.config.config_loader import JSONConfigurationFile, YAMLConfigurationFile
import hashlib
import requests
import tempfile
import tarfile
import shutil
import re

import yaml

SERVER_CONFIG_SCHEMA = {
    "server_type": str,
    "server_ip": str,
    "server_port": int,
    "server_password": str,
    "server_mod": str,
    "startup_configs": list
}

SERVER_CONFIG_DEFAULTS = {
    "server_type": "etl",
    "server_ip": "0.0.0.0",
    "server_port": 27960,
    "server_password": "",
    "server_mod": "legacy",
    "startup_configs": [
        "etl_server.cfg"
    ]
}

def sizeof_fmt(num, suffix="B"):
    num = int(num)
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

def md5sum(filepath, default=None):
    if isinstance(filepath, Path):
        filepath = str(filepath)
    if not os.path.exists(filepath):
        return default
    with open(filepath, "rb") as f:
        file_hash = hashlib.md5()
        chunk = f.read(8192)
        while chunk:
            file_hash.update(chunk)
            chunk = f.read(8192)
    return file_hash.hexdigest()


class SourcesManager:
    """
    Manage sources
    """
    def __init__(self, debug: bool = False, sources_url: str = None):
        """
        :param debug: Enable debug mode
        """
        if sources_url is None:
            sources_url = "http://etsm.symnet.io"
        if sources_url.endswith("/"):
            sources_url = sources_url[:-1]
        self.sources_url = sources_url
        self.logger = Logging("etsm", "sources", debug=debug).get_logger()
        self.debug = debug
        self.sources_dir = Path("/var/lib/etsm/source")
        self.index = None
        self.get_index()
        if self.index is None:
            self.logger.error("Failed to get remote index")
        if "etsm" not in self.index:
            self.logger.error("Failed to get remote index")

    def download_file_progress(self, url, destination):
        with open(destination, "wb") as f:
            self.logger.info("Downloading %s" % url)
            response = requests.get(url, stream=True)
            if response.status_code != 200:
                self.logger.error("Failed to download %s: HTTP %s" % (url, response.status_code))
                return
            total_length = response.headers.get('content-length')
            total_length_h = sizeof_fmt(total_length)
            if total_length is None: # no content length header
                self.logger.debug("No content length header")
                dl = 0
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    done = int(50 * dl / total_length)
                    sys.stdout.write("\rDownloaded %s ..." % (sizeof_fmt(dl)) )    
                    sys.stdout.flush()
            else:
                dl = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    done = int(50 * dl / total_length)
                    sys.stdout.write("\rProgress: [%s%s] (%s/%s)       " % ('=' * done, ' ' * (50-done), sizeof_fmt(dl), total_length_h) )    
                    sys.stdout.flush()
        print("")
        return True

    def get_index(self):
        """
        Get the index of sources
        :return: Index of sources
        """
        self.logger.debug("Getting sources index ...")
        res = requests.get(self.sources_url + "/index.yaml")
        if res.status_code == 200:
            with tempfile.NamedTemporaryFile() as f:
                f.write(res.content)
                f.seek(0)
                try:
                    index = YAMLConfigurationFile(f.name, schema={ "etsm": { "config_templates": str }, "servers": {} })
                    self.index = index
                except yaml.parser.ParserError:
                    self.logger.error("Failed to parse remote index file")
        else:
            self.logger.error("Failed to get index of sources: HTTP {}".format(res.status_code))

    def download_paks(self):
        self.logger.info("Downloading etmain paks ...")
        destination_path = Path("/var/lib/etsm/source/servers")
        if not self.download_file_progress(self.sources_url + self.index["etsm"]["paks"], destination_path / "paks.tgz"):
            self.logger.error("Failed to download etmain paks!")
            return
        etmain_dir = destination_path / "etmain"
        if not etmain_dir.exists():
            etmain_dir.mkdir()
        self.logger.info("Extracting etmain paks...")
        with tarfile.open(destination_path / "paks.tgz", "r:gz") as tar:
            tar.extractall(etmain_dir)

    def download_server_sources(self, all_versions: bool = False):
        self.logger.info("Downloading server sources...")
        destination_path = Path("/var/lib/etsm/source/servers")
        if not destination_path.exists():
            destination_path.mkdir(parents=True)
        if self.index is not None:
            for s_type, s_info in self.index["etsm"]["servers"].items():
                if all_versions:
                    self.logger.info("Downloading all versions for server type: %s" % s_type)
                    for version, v_info in s_info["versions"].items():
                        r_chk = v_info["server_archive_md5"]
                        if md5sum(destination_path / (s_type + "-" + version + ".tgz")) != r_chk:
                            self.logger.info("Downloading {} server version {}".format(s_type, version))
                            self.download_file_progress(self.sources_url + v_info["server_archive"], destination_path / (s_type + "-" + version + ".tgz"))
                        else:
                            self.logger.info("{} server version {} already downloaded".format(s_type, version))
                else:
                    self.logger.info("Downloading latest sources for server type {}".format(s_type))
                    latest_version = s_info["latest"]
                    latest_info = s_info["versions"][latest_version]
                    r_chk = latest_info["server_archive_md5"]
                    if md5sum(destination_path / (s_type + "-" + latest_version + ".tgz")) != r_chk:
                        self.download_file_progress(self.sources_url + latest_info["server_archive"], str(destination_path.joinpath("%s-%s.tgz" % (s_type, latest_version))))
                    else:
                        self.logger.info("{} server version {} already downloaded".format(s_type, latest_version))

    def download_maps(self, maps: list):
        if isinstance(maps, str):
            maps = [maps]
        self.logger.info("Downloading maps %s ..." % maps)
        destination_path = Path("/var/lib/etsm/source/maps")
        if not destination_path.exists():
            destination_path.mkdir(parents=True)
        for _map in maps:
            if not _map.endswith(".pk3"):
                _map += ".pk3"
            self.logger.info("Downloading map %s" % _map)
            destination_map_path = destination_path / _map
            if not destination_map_path.exists():
                self.download_file_progress(self.sources_url + "/maps/" + _map, destination_map_path)
            else:
                self.logger.info("Map %s already downloaded" % _map)

    def download_mod_sources(self, all_versions: bool = False):
        self.logger.info("Downloading mod sources...")
        destination_path = Path("/var/lib/etsm/source/mods")
        if not destination_path.exists():
            destination_path.mkdir(parents=True)
        if self.index is not None:
            for m_type, m_info in self.index["etsm"]["mods"].items():
                if all_versions:
                    self.logger.info("Downloading all versions for mod type: %s" % m_type)
                    for version, v_info in m_info["versions"].items():
                        r_chk = v_info["mod_archive_md5"]
                        if md5sum(destination_path / (m_type + "-" + version + ".tgz")) != r_chk:
                            self.logger.info("Downloading {} mod version {}".format(m_type, version))
                            self.download_file_progress(self.sources_url + v_info["mod_archive"], destination_path / (m_type + "-" + version + ".tgz"))
                        else:
                            self.logger.info("{} mod version {} already downloaded".format(m_type, version))
                else:
                    self.logger.info("Downloading latest sources for mod type {}".format(m_type))
                    latest_version = m_info["latest"]
                    latest_info = m_info["versions"][latest_version]
                    r_chk = latest_info["mod_archive_md5"]
                    if md5sum(destination_path / (m_type + "-" + latest_version + ".tgz")) != r_chk:
                        self.download_file_progress(self.sources_url + latest_info["mod_archive"], str(destination_path.joinpath("%s-%s.tgz" % (m_type, latest_version))))
                    else:
                        self.logger.info("{} mod version {} already downloaded".format(m_type, latest_version))


    def download_config_templates(self):
        self.logger.info("Downloading config templates...")
        destination_path = Path("/var/lib/etsm/source/config_templates")
        if not destination_path.exists():
            destination_path.mkdir(parents=True)
        if self.index is not None:
            with tempfile.NamedTemporaryFile() as f:
                if self.download_file_progress(self.sources_url + self.index["etsm"]["config_templates"], f.name):
                    self.logger.info("Extracting config templates...")
                    with tarfile.open(f.name, "r") as tar:
                        tar.extractall(destination_path)
                    checksum_path = destination_path / "checksums.md5"
                    if checksum_path.exists():
                        checksum_path.unlink()
                    with open(checksum_path, "w") as f:
                        f.write(self.index["etsm"]["config_templates_md5"])
                else:
                    self.logger.error("Failed to download config templates")

    def download_systemd_file(self):
        self.logger.info("Downloading systemd template file...")
        destination_path = self.sources_dir / "systemd"
        if not destination_path.exists():
            destination_path.mkdir(parents=True)
        if self.index is not None:
            self.download_file_progress(self.sources_url + self.index["etsm"]["systemd_template"], destination_path / "systemd.service.template")

    def download_sources(self, all_versions: bool = False, download_maps: bool = False):
        if not self.sources_dir.exists():
            servers_dir = self.sources_dir / "servers"
            servers_dir.mkdir(parents=True)
            config_dir = self.sources_dir / "config_templates"
            config_dir.mkdir(parents=True)
        r_chk = self.index["etsm"]["paks_md5"]
        if md5sum("/var/lib/etsm/source/servers/paks.tgz") != r_chk:
            self.download_paks()
        else:
            self.logger.info("etmain sources are up to date")
        self.download_server_sources(all_versions=all_versions)
        self.download_mod_sources(all_versions=all_versions)
        r_chk = self.index["etsm"]["config_templates_md5"]
        chk_path = Path("/var/lib/etsm/source/config_templates/checksums.md5")
        l_chk = None
        if chk_path.exists():
            with open(chk_path, "r") as f:
                l_chk = f.read()
        self.download_systemd_file()
        if l_chk != r_chk:
            self.download_config_templates()
        else:
            self.logger.info("Config templates are up to date")
        if download_maps:
            self.logger.info("Downloading maps...")
            self.download_maps(self.index["etsm"]["maps"])

    def build_sources_archive(self):
        self.logger.info("Building sources archive...")


class ServerManager:
    def __init__(self, server_name: str = None, debug: bool = False):
        self.server_name = server_name
        if self.server_name is None:
            self.server_name = "default"
        if not re.match(r'^[A-Za-z0-9_]+$', self.server_name):
            raise SyntaxError("Invalid server name: %s (Must match " % self.server_name)
            
        self.logger = Logging("etsm", self.server_name, debug=debug).get_logger()
        self.home_path = Path("/var/lib/etsm")
        self.source_path = self.home_path / "source"
        self.server_path = self.home_path / "servers" / self.server_name
        self.config_path = self.server_path / "etsm_configs"
        self.home_path.mkdir(parents=True, exist_ok=True)
        self.server_path.mkdir(parents=True, exist_ok=True)
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.etsm_config_path = self.server_path / ".etsm_config"
        self.config = JSONConfigurationFile(self.etsm_config_path, schema=SERVER_CONFIG_SCHEMA, auto_create=SERVER_CONFIG_DEFAULTS)
        self.mod_path = self.server_path / self.config["server_mod"]

    def run_server(self):
        args = self.build_startup_args()
        self.logger.info("Starting server...")
        self.logger.debug("Args: %s" % args)
        # command = "/bin/bash -c '{}'".format(" ".join(args))
        # pidfile = self.server_path / "legacy" / "etlegacy_server.pid"
        # pidfile.touch()
        subprocess.run(" ".join(args), shell=True, cwd=str(self.server_path))

    def set_mod(self, mod_name: str):
        self.logger.info("Setting mod to %s" % mod_name)
        mod_path = self.server_path / mod_name
        if not mod_path.exists():
            self.logger.warn("Mod %s does not exist in server %s" % (mod_name, self.server_name))
        self.config["server_mod"] = mod_name
        self.config.write()
        self.build_systemd_file()

    def set_ip(self, ip: str):
        self.logger.info("Setting ip to %s" % ip)
        self.config["server_ip"] = ip
        self.config.write()
        self.build_systemd_file()
    
    def set_port(self, port: int):
        self.logger.info("Setting port to %s" % port)
        self.config["server_port"] = port
        self.config.write()
        self.build_systemd_file()

    def build_startup_args(self):
        args = [
            str(self.server_path / "etlded"),
            "+set fs_homepath %s" % self.server_path,
            "+set fs_basepath %s" % self.server_path,
            "+set net_ip %s" % self.config["server_ip"],
            "+set net_port %s" % self.config["server_port"],
            "+set fs_game %s" % self.config["server_mod"],
            "+set dedicated 2"
        ]
        for conf in self.config["startup_configs"]:
            if not re.match(r"^[A-Za-z0-9._]+$", conf):
                self.logger.error("Invalid config name: {}".format(conf))
                continue
            args.append("+exec %s" % conf)
        return args

    def update_server(self, source_version: str = None, force: bool = False):
        if source_version is None:
            source_version = "2.80.1"
        self.logger.info("Updating server to version {} ...".format(source_version))
        if self.config["installed_version"] != source_version or force:
            tarname = "{}-{}.tgz".format(self.config["server_type"], source_version)
            with tempfile.TemporaryDirectory() as tmpdirname:
                with tarfile.open(self.source_path / "servers" / tarname) as tar:
                    tar.extractall(tmpdirname)
                self.logger.debug("Extracted {} to {}".format(tarname, tmpdirname))
                etl_dirname = "etlegacy-v{}-i386".format(source_version)
                etl_path = Path(tmpdirname) / etl_dirname
                shutil.copytree(etl_path, self.server_path, dirs_exist_ok=True)
            self.config["installed_version"] = source_version
            self.config.write()
            self.logger.info("Server mod updated to version {}.".format(source_version))
        else:
            self.logger.info("Server mod is already up to date.")
        # only unpack pk3s if necessary
        etmain_path = self.server_path / "etmain"
        pak0 = etmain_path / "pak0.pk3"
        pak1 = etmain_path / "pak1.pk3"
        pak2 = etmain_path / "pak2.pk3"
        if not pak0.exists() or not pak1.exists() or not pak2.exists():
            self.logger.info("Linking etmain paks...")
            s_pak0 = self.source_path / "servers" / "etmain" / "pak0.pk3"
            s_pak1 = self.source_path / "servers" / "etmain" / "pak1.pk3"
            s_pak2 = self.source_path / "servers" / "etmain" / "pak2.pk3"
            if not s_pak0.exists() or not s_pak1.exists() or not s_pak2.exists():
                self.logger.error("Source etmain paks are missing. Try updating sources ...")
                return
            pak0.symlink_to(s_pak0)
            pak1.symlink_to(s_pak1)
            pak2.symlink_to(s_pak2)
        else:
            self.logger.info("etmain paks are already linked.")

    def get_config_path(self, config_name: str):
        if not config_name.endswith(".cfg"):
            config_name += ".cfg"
        return self.config_path / config_name

    def get_config(self, config_name: str):
        config_path = self.get_config_path(config_name)
        if not config_path.exists():
            self.logger.error("Config file {} does not exist.".format(config_path))
            return
        with open(config_path, "r") as f:
            config = f.read()
        return config

    def get_pk3_maps(self, maps: list):
        pk3_maps = []
        for _map in maps:
            map_path = self.source_path / "maps" / (_map + ".pk3")
            if map_path.exists():
                with ZipFile(map_path, "r") as z:
                    for name in z.namelist():
                        if name.startswith("maps/") and name.endswith(".bsp"):
                            matches = re.match(r"maps/(.*)\.bsp", name)
                            pk3_maps.append(matches.group(1))
        return pk3_maps

    def build_mapvote_cycle(self, real_mapnames: bool = False):
        """
        Builds a mapvote cycle from the currently enabled maps
        :param real_mapnames: if True, the mapnames will be read from the pk3 files. This will be slower, but ensure proper map names. If false, etsm will make a best guess based on the pk3 filename. 
        """
        etmain_path = self.server_path / "etmain" / "mapvotecycle.cfg"
        if etmain_path.exists():
            if not etmain_path.is_symlink():
                ts = int(time.time())
                new_path = self.server_path / "etmain" / "mapvotecycle-{}.cfg".format(ts)
                self.logger.info("mapvotecycle.cfg is not a symlink. Moving it to %s." % new_path)
                etmain_path.rename(new_path)
        self.logger.info("Building mapvote cycle config ...")
        config = "// Mapvote cycle (Generated by etsm)\n"
        config += "// Create Time %s\n\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        maps = self.list_enabled_maps()
        if real_mapnames:
            maps = self.get_pk3_maps(maps)
        for i, _map in enumerate(maps):
            config += "set d%d \"set g_gametype 6 ; map %s ; set nextmap vstr d%d\"\n" % (i, _map.lower(), (i + 1))
        config += "vstr d0\n"
        # need to write config too
        config_path = self.get_config_path("mapvotecycle")
        if config_path.exists():
            config_path.unlink()
        with open(config_path, "w") as f:
            f.write(config)
        self.logger.info("Mapvote cycle config written!")
        self.activate_config("mapvotecycle")

    def add_map(self, map_name: str):
        if not map_name.endswith(".pk3"):
            map_name += ".pk3"
        self.logger.info("Adding map {}...".format(map_name))
        dest_path = self.server_path / "etmain" / map_name
        if dest_path.exists():
            self.logger.warn("Map {} already enabled.".format(map_name))
            return
        src_path = self.source_path / "maps" / map_name
        if not src_path.exists():
            self.logger.error("Source map {} does not exist.".format(map_name))
            return
        dest_path.symlink_to(src_path)

    def remove_map(self, map_name: str):
        if not map_name.endswith(".pk3"):
            map_name += ".pk3"
        self.logger.info("Removing map {}...".format(map_name))
        dest_path = self.server_path / "maps" / map_name
        if not dest_path.exists():
            self.logger.warn("Map {} not enabled.".format(map_name))
            return
        dest_path.unlink()

    def activate_config(self, config_name: str):
        config_path = self.get_config_path(config_name)
        if not config_path.exists():
            self.logger.error("Config file {} does not exist.".format(config_name))
            return
        destination = self.server_path / "etmain" / config_path.name
        if destination.exists():
            self.logger.info("Config {} already activated.".format(config_name))
            return
        self.logger.info("Activating config {} ...".format(config_name))
        os.symlink(config_path, destination)

    def deactivate_config(self, config_name: str):
        config_path = self.server_path / "etmain" / config_path.name
        if not config_path.exists():
            self.logger.error("Config file {} does not exist.".format(config_name))
            return
        self.logger.info("Deactivating config {} ...".format(config_name))
        os.unlink(self.server_path / "etmain" / config_path.name)

    def list_cvars(self, config_name: str):
        config = self.get_config(config_name)
        if config is None:
            return
        search_string = r"^set\s+(\w+).*$"
        matches = re.findall(search_string, config, re.MULTILINE)
        if len(matches) == 0:
            self.logger.warn("No CVars found in {}.".format(config_name))
            return
        return matches

    def list_execs(self, config_name: str):
        config = self.get_config(config_name)
        if config is None:
            return
        search_string = r"^exec\s+(\w+).*$"
        matches = re.findall(search_string, config, re.MULTILINE)
        if len(matches) == 0:
            self.logger.warn("No Execs found in {}.".format(config_name))
            return
        return matches

    def list_configs(self):
        return [x.name[:-len(".cfg")] for x in self.config_path.iterdir() if x.is_file() and x.name.endswith(".cfg")]

    def list_active_configs(self):
        return [x.name[:-len(".cfg")] for x in (self.server_path / "etmain").iterdir() if x.is_symlink() and x.name.endswith(".cfg")]

    def list_templates(self):
        return [x.name[:-len(".cfg")] for x in (self.source_path / "config_templates").iterdir() if x.is_file() and x.name.endswith(".cfg")]

    def list_mods(self):
        mods = [x.name[:-len(".tgz")] for x in (self.source_path / "mods").iterdir() if x.is_file() and x.name.endswith(".tgz")]
        final = []
        for mod in mods:
            final.append(mod.split("-", 1)[0])
        return final

    def list_enabled_maps(self):
        pk3s = [x.name[:-len(".pk3")] for x in (self.server_path / "etmain").iterdir() if not x.is_dir() and x.name.endswith(".pk3")]
        # Remove etmain paks
        pk3s.remove("pak0")
        pk3s.remove("pak1")
        pk3s.remove("pak2")
        return pk3s

    def list_available_maps(self):
        return [x.name[:-len(".pk3")] for x in (self.source_path / "maps").iterdir() if x.is_file() and x.name.endswith(".pk3")]

    def get_cvar(self, config_name: str, cvar: str):
        config = self.get_config(config_name)
        line_to_search = r'^set\s+%s\s+"(.*)".*$' % cvar
        matches = re.findall(line_to_search, config, re.MULTILINE)
        if len(matches) == 0:
            self.logger.warn("CVar {} does not exist in {}.".format(cvar, config_name))
            return None
        return matches[-1]

    def create_config(self, config_name: str, cvars: dict = None, from_template: str = None, activate: bool = False):
        config_path = self.get_config_path(config_name)
        if config_path.exists():
            self.logger.error("Config file {} already exists.".format(config_name))
            return
        if from_template is not None:
            if not from_template.endswith(".cfg"):
                from_template += ".cfg"
            template_path = self.source_path / "config_templates" / from_template
            if not template_path.exists():
                self.logger.error("Template file {} does not exist.".format(template_path))
                return
            shutil.copy(template_path, str(config_path))
        if cvars is None:
            cvars = {}
        self.update_cvars(config_name, cvars)
        if activate:
            self.activate_config(config_name)

    def update_cvars(self, config_name: str, new_values: dict):
        config_path = self.get_config_path(config_name)
        config = self.get_config(config_name)
        self.logger.info("Updating config {} ...".format(config_path))
        if not config_path.exists():
            if not config_path.parent.exists():
                self.logger.error("Server [%s] is missing 'etmain' directory. You may need to update the server." % self.server_name)
                return
            self.logger.warn("Config file {} does not exist. Automatically creating...".format(config_path))
            config = "// Config file generated by etsm\n"
            config += "// Create Time: %s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(config_path, "w") as f:
                f.write(config)
            
        for key, value in new_values.items():
            self.logger.info("Updating {} to {}".format(key, value))
            new_line = "set %s \"%s\" // cvar updated by etsm" % (key, value)
            self.logger.debug("New line: {}".format(new_line))
            if key in config:
                line_to_replace = r"^set\s+%s.*$" % key
                config = re.sub(line_to_replace, new_line, config, flags=re.MULTILINE)
            else:
                self.logger.warn("CVar {} does not exist in {}, adding".format(key, config_path))
                config += "%s\n" % new_line
        with open(config_path, "w") as f:
            f.write(config)

    def update_bots(self, config_name: str, new_values: dict):
        config_path = self.get_config_path(config_name)
        config = self.get_config(config_name)
        self.logger.info("Updating config {} ...".format(config_path))
        if not config_path.exists():
            if not config_path.parent.exists():
                self.logger.error("Server [%s] is missing 'etmain' directory. You may need to update the server." % self.server_name)
                return
            self.logger.warn("Config file {} does not exist. Automatically creating...".format(config_path))
            config = "// Config file generated by etsm\n"
            config += "// Create Time: %s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(config_path, "w") as f:
                f.write(config)

        for key, value in new_values.items():
            self.logger.info("Updating {} to {}".format(key, value))
            new_line = "bot %s %s // bot config updated by etsm" % (key, value)
            self.logger.debug("New line: {}".format(new_line))
            if key in config:
                line_to_replace = r"^bot\s+%s.*$" % key
                config = re.sub(line_to_replace, new_line, config, flags=re.MULTILINE)
            else:
                self.logger.warn("Bot configuration {} does not exist in {}, adding".format(key, config_path))
                config += "%s\n" % new_line
        with open(config_path, "w") as f:
            f.write(config)

    def add_exec(self, config_name: str, exec_name: str):
        config_path = self.get_config_path(config_name)
        config = self.get_config(config_name)
        self.logger.info("Adding exec {} to {}".format(exec_name, config_name))
        if not config_path.exists():
            if not config_path.parent.exists():
                self.logger.error("Server [%s] is missing 'etmain' directory. You may need to update the server." % self.server_name)
                return
            self.logger.warn("Config file {} does not exist. Automatically creating...".format(config_path))
            config = "// Config file generated by etsm\n"
            config += "// Create Time: %s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(config_path, "w") as f:
                f.write(config)
        
        new_line = "exec %s // exec added by etsm\n" % exec_name
        self.logger.debug("New line: {}".format(new_line))
        matches = re.findall(r"^exec\s+\w+.*$", config, re.MULTILINE)
        if len(matches) > 0:
            self.logger.warn("Exec {} already exists in {}, skipping".format(exec_name, config_path))
            return
        config += new_line
        with open(config_path, "w") as f:
            f.write(config)

    def remove_exec(self, config_name: str, exec_name: str):
        config_path = self.get_config_path(config_name)
        config = self.get_config(config_name)
        self.logger.info("Removing exec {} from {}".format(exec_name, config_name))
        if not config_path.exists():
            self.logger.error("Config file {} does not exist!".format(config_path))
            return
        line_to_remove = r"^exec\s+%s.*$" % exec_name
        config = re.sub(line_to_remove, "", config, flags=re.MULTILINE)
        with open(config_path, "w") as f:
            f.write(config)

    def config_activated(self, config_name: str):
        if not config_name.endswith(".cfg"):
            config_name += ".cfg"
        config_path = self.server_path / "etmain" / config_name
        return config_path.exists()

    def build_systemd_file(self):
        self.logger.info("(re)building systemd file ...")
        systemd_template_file = self.source_path / "systemd" / "systemd.service.template"
        if not systemd_template_file.exists():
            self.logger.error("Systemd template source file does not exist!")
            return
        systemd_file_name = self.server_name + ".service"
        systemd_file_path = self.server_path / "systemd" / systemd_file_name
        systemd_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(systemd_template_file, "r") as f:
            template = f.read()
        systemd_template = Template(template)
        data = {
            "server_name": self.server_name,
            "startup_command": " ".join(self.build_startup_args()),
        }
        systemd_file_content = systemd_template.substitute(data)
        with open(systemd_file_path, "w") as f:
            f.write(systemd_file_content)

    def link_systemd_file(self):
        self.build_systemd_file()
        self.logger.info("linking systemd file ...")
        systemd_file_name = self.server_name + ".service"
        systemd_file_path = self.server_path / "systemd" / systemd_file_name
        destination_path = Path("/etc/systemd/system") / systemd_file_name
        if destination_path.exists():
            self.logger.info("Systemd file already exists, removing ...")
            destination_path.unlink()
        if not systemd_file_path.exists():
            self.logger.error("Systemd file does not exist!")
            return
        try:
            destination_path.symlink_to(systemd_file_path)
        except PermissionError:
            self.logger.error("Cannot link systemd file: %s. (You may need to run this as root)" % systemd_file_name)

    def reload_systemd(self):
        self.logger.info("reloading systemd ...")
        subprocess.run(["systemctl", "daemon-reload"])

    def add_startup_config(self, config_name: str):
        if not re.match(r"^[A-Za-z0-9._]+$", config_name):
            self.logger.error("Invalid config name: {}".format(config_name))
            return
        if not config_name.endswith(".cfg"):
            config_name += ".cfg"
        if not self.config_activated(config_name):
            self.logger.warn("Config {} is not activated.".format(config_name))
        self.config["startup_configs"].append(config_name)
        self.config.write()
        self.logger.info("Added {} to startup configs.".format(config_name))

    def remove_startup_config(self, config_name: str):
        if not config_name.endswith(".cfg"):
            config_name += ".cfg"
        if config_name not in self.config["startup_configs"]:
            self.logger.warn("Config {} is not in startup configs.".format(config_name))
            return
        self.config["startup_configs"].remove(config_name)
        self.config.write()
        self.logger.info("Removed {} from startup configs.".format(config_name))

    def install_mod(self, mod_name: str, mod_version: str = None, force: bool = False):
        if mod_version is None:
            sm = SourcesManager()
            if sm.index is not None:
                mod_version = sm.index["etsm"]["mods"][mod_name]["latest"]
            else:
                self.logger.error("No mod version passed and no index found. Aborting.")
                return
        self.logger.info("Installing mod {} version {}...".format(mod_name, mod_version))
        mod_path = self.source_path / "mods" / (mod_name + "-" + mod_version + ".tgz")
        if not mod_path.exists():
            self.logger.error("Source mod archive does not exist: {}".format(mod_path))
            return
        mod_dest_path = self.server_path / mod_name
        if mod_dest_path.exists():
            installed_version_path = mod_dest_path / ".mod_version"
            if installed_version_path.exists():
                with open(installed_version_path, "r") as f:
                    installed_version = f.read().strip()
                if installed_version == mod_version:
                    self.logger.warn("Mod {} already exists at version {}, not installing. Pass force argument to force installation.".format(mod_name, mod_version))
                    return
        with tarfile.open(mod_path, "r:gz") as f:
            f.extractall(self.server_path)
        with open(mod_dest_path / ".mod_version", "w") as f:
            f.write(mod_version)
        self.logger.info("Mod {} version {} installed.".format(mod_name, mod_version))
