"""
Base class for LLM clients.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseLLMClient(ABC):
    """LLMクライアントの抽象基底クラス"""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """
        メッセージを送信してレスポンスを取得

        Args:
            messages: チャットメッセージのリスト
                      各メッセージは {"role": "user"|"assistant"|"system", "content": "..."}
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            LLMからのレスポンステキスト
        """
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """
        プロンプトからテキスト生成

        Args:
            prompt: 生成のためのプロンプト
            model: 使用するモデル名（省略時はデフォルトモデルを使用）

        Returns:
            生成されたテキスト
        """
        pass


class LLMError(Exception):
    """LLM API呼び出しエラー"""

    pass
