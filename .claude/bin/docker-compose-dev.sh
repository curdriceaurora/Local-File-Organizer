#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
cd /Users/rahul/Projects/Local-File-Organizer
exec /usr/local/bin/docker compose -f docker-compose.yml -f docker-compose.dev.yml up
