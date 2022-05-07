#!/usr/bin/env bash

set -x

# Cleanup /var/lib/etsm for testing
if [ "$1" = "clean" ]; then
    rm -rf /var/lib/etsm/source/
    rm -rf /var/lib/etsm/servers/
fi

etsm sources update
etsm server create
etsm server config create --from-template etl_server myserver
etsm server config set myserver sv_hostname "Test Server"
etsm server config activate myserver
etsm server config remove-startup-config etl_server
etsm server config add-startup-config myserver
etsm server run
