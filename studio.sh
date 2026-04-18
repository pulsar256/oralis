#!/usr/bin/env bash
# Usage: bash studio.sh [uvicorn args]
# Set UV_BACKEND to override the torch backend (default: cuda)
# Set LOG_LEVEL to override log level (default: info; use debug for TTS pass-through logging)
BACKEND="${UV_BACKEND:-cuda}"
LOG_LEVEL="${LOG_LEVEL:-info}"
exec uv run --extra "$BACKEND" studio --log-level "$LOG_LEVEL" "$@"
