#!/bin/bash
# Wrapper for launchd — unattended run, zero interactive prompts (--auto
# never asks for confirmation), safe to schedule.
set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate
python3 run_agent.py --auto
