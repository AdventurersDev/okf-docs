#!/usr/bin/env bash
# Workspace: the app fixture, a small invoicing API with no docs.
exec bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" app
