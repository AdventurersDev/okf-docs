#!/usr/bin/env bash
# Workspace: the repo fixture, a small export service with a docs bundle and no AGENTS.md.
exec bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" repo
