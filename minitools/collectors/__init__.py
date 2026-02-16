"""
Data collectors for various content sources.
"""

from minitools.collectors.arxiv import ArxivCollector
from minitools.collectors.medium import MediumCollector
from minitools.collectors.google_alerts import GoogleAlertsCollector
from minitools.collectors.x_trend import XTrendCollector

# YouTubeCollectorは条件付きでインポート
try:
    from minitools.collectors.youtube import YouTubeCollector

    __all__ = [
        "ArxivCollector",
        "MediumCollector",
        "GoogleAlertsCollector",
        "YouTubeCollector",
        "XTrendCollector",
    ]
except ImportError:
    # mlx_whisperがインストールされていない場合
    __all__ = [
        "ArxivCollector",
        "MediumCollector",
        "GoogleAlertsCollector",
        "XTrendCollector",
    ]
