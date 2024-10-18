#!/bin/bash
# Load environment variables
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Run the Python script using Poetry
poetry run python src/get_arxiv_summary_in_japanese.py
