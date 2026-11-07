#!/bin/sh
set -eu
openmukti_folder=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$openmukti_folder/Openmukti.pyw"
