#!/usr/bin/env bash
# Wrapper for global write-pending-ci.sh (webhook subsystem)
# Core logic extracted to ~/.factory/webhook/scripts/write-pending-ci.sh
# This wrapper maintains backward compatibility for existing SKILL.md references
exec ~/.factory/webhook/scripts/write-pending-ci.sh "$@"
