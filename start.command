#!/usr/bin/env bash
# Double-click this in Finder to run the app.
# Finder starts scripts from an arbitrary directory, so cd to this file's own
# folder before doing anything.
cd "$(dirname "$0")" || exit 1
exec bash scripts/dev.sh
