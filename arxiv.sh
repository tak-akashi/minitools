#!/bin/bash
# Load environment variables
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Run the Python script using Poetry
uv run script/get_arxiv_summary_in_japanese.py
