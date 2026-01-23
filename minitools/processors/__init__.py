"""
Content processors for translation and summarization.
"""

from minitools.processors.translator import Translator
from minitools.processors.summarizer import Summarizer
from minitools.processors.weekly_digest import WeeklyDigestProcessor
from minitools.processors.duplicate_detector import (
    DuplicateDetector,
    deduplicate_articles,
)

__all__ = [
    "Translator",
    "Summarizer",
    "WeeklyDigestProcessor",
    "DuplicateDetector",
    "deduplicate_articles",
]