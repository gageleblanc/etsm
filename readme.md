# etsm

ETSM is a project I started after getting tired of trying to set up Enemy Territory servers every few years without all of the assets/tools/etc I need. 
The goal of this project is to make it exceedingly easy to deploy an Enemy Territory server in moments. 
Note that this tool is only intended to work with the [Enemy Territory: Legacy project](https://www.etlegacy.com) servers.

## ETSM Configuration
ETSM is able to run without any configuration changes, however you may want to change the "default_server" configuration option in order to more accurately track the default server you are working with.
You are able to run ETSM commands on any server with the `--server-name` flag.
```
$ etsm config set default_server <server_name>
```

## Sources
By default, ETSM will download what it needs to start making servers when you run the following:
```
$ etsm sources update
```
This command will, by default, download the minimal requirements for running ETL servers. This includes:

* ET Legacy
* etmain paks (pak0, pak1, pak2)
* Template config files (server configs, mod configs)

You can optionally download every version of each mod as well as every version of ET Legacy if you prefer, by adding the `--all-versions` argument to the `update` command.
You may optionally also download all of the maps available from the ETSM s3 bucket by adding `--download-maps` as well.

## Maps 
You may also download maps with the following command:
```
$ etsm server map download <map name> [<map name> ...]
```
Note that this will only download the maps into the ETSM sources directory, in order to activate a map on a server, you will need to run the following:
```
$ etsm server map add <map name>
```
You may search for maps available on the remote repository (by default, https://etsm.symnet.io), by using the `search` command as follows:
```
$ etsm sources map search <search term>
```

## Configuration
ETSM aims to make configuring an Enemy Territory server a little bit easier than normal. You can change cvars in any config with a command like so:
```
$ etsm server config set <config name> <cvar> <value>
```
This will result in ETSM searching the config file for the cvar and updating it if it exists, and if not it will add the cvar to the bottom of the config file.

Similarly, you can add `exec` commands to the configuration file like this:
```
$ etsm server config exec <config name>
```
You may also set Omni-bot options via the `bot` subcommand of the `config` command.

ETSM will by default set your server to listen on `0.0.0.0:27960` running the legacy mod, however this behavior can be changed with the following commands:
* `etsm server config set-ip <ip>`
* `etsm server config set-port <port>`
* `etsm server config set-mod <mod name>`

## Mods
You may set the server mod with the above `set-mod` command, or you can use the `mod` subcommand, like so:
```
$ etsm server mod set <mod name>
```
You may also list available mods to install with the `list` subcommand, and install them to the server with the `install` subcommand, like so:
```
$ etsm server mod install <mod name>
```

### Notes
* ETSM tries to save space on your hard disk by using symbolic links to link needed files into servers rather than copying them. This is also how configs are activated and de-activated
* ETSM will by default manage a server called 'default'. You can change this with the `--server-name` argument on most subcommands. You can also configure a default server with the `etsm config` command.
