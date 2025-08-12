"""
Minitools - A collection of automation tools for content aggregation and processing.

This package provides tools for:
- Collecting content from various sources (ArXiv, Medium, Google Alerts, YouTube)
- Processing and translating content
- Publishing to Notion and Slack
"""

__version__ = "0.1.0"
__author__ = "minitools"

from minitools.utils.logger import setup_logger, get_logger

__all__ = [
    "setup_logger",
    "get_logger",
]