"""
Embedding client abstraction layer.
Provides a unified interface for different embedding providers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from minitools.utils.config import get_config
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingError(Exception):
    """Embedding API呼び出しエラー"""

    pass


class BaseEmbeddingClient(ABC):
    """Embeddingクライアントの抽象基底クラス"""

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        テキストリストをEmbeddingベクトルに変換

        Args:
            texts: 変換するテキストのリスト

        Returns:
            各テキストに対応するEmbeddingベクトルのリスト
        """
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """
        単一テキストをEmbeddingベクトルに変換

        Args:
            text: 変換するテキスト

        Returns:
            Embeddingベクトル
        """
        pass


class OllamaEmbeddingClient(BaseEmbeddingClient):
    """Ollama Embeddingクライアント（nomic-embed-text使用）"""

    def __init__(self, model: Optional[str] = None):
        """
        Args:
            model: 使用するEmbeddingモデル名（省略時はnomic-embed-text）
        """
        config = get_config()
        self.model = model or config.get(
            "weekly_digest.deduplication.embedding_model", "nomic-embed-text"
        )
        self._embeddings = None
        logger.debug(f"OllamaEmbeddingClient initialized with model: {self.model}")

    def _get_embeddings(self):
        """OllamaEmbeddingsインスタンスを取得（遅延初期化）"""
        if self._embeddings is None:
            try:
                from langchain_ollama import OllamaEmbeddings

                self._embeddings = OllamaEmbeddings(model=self.model)
            except ImportError as e:
                raise EmbeddingError(
                    f"langchain-ollama is required for Ollama embeddings: {e}"
                )
        return self._embeddings

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        テキストリストをEmbeddingベクトルに変換

        Args:
            texts: 変換するテキストのリスト

        Returns:
            各テキストに対応するEmbeddingベクトルのリスト

        Raises:
            EmbeddingError: Embedding生成に失敗した場合
        """
        if not texts:
            return []

        try:
            embeddings = self._get_embeddings()
            result = await embeddings.aembed_documents(texts)
            logger.debug(f"Generated {len(result)} embeddings via Ollama")
            return result
        except Exception as e:
            logger.error(f"Ollama embedding error: {e}")
            raise EmbeddingError(f"Ollama embedding failed: {e}") from e

    async def embed_text(self, text: str) -> List[float]:
        """
        単一テキストをEmbeddingベクトルに変換

        Args:
            text: 変換するテキスト

        Returns:
            Embeddingベクトル

        Raises:
            EmbeddingError: Embedding生成に失敗した場合
        """
        try:
            embeddings = self._get_embeddings()
            result = await embeddings.aembed_query(text)
            logger.debug(f"Generated single embedding via Ollama (dim={len(result)})")
            return result
        except Exception as e:
            logger.error(f"Ollama embedding error: {e}")
            raise EmbeddingError(f"Ollama embedding failed: {e}") from e


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """OpenAI Embeddingクライアント（text-embedding-3-small使用）"""

    def __init__(self, model: Optional[str] = None):
        """
        Args:
            model: 使用するEmbeddingモデル名（省略時はtext-embedding-3-small）
        """
        self.model = model or "text-embedding-3-small"
        self._embeddings = None
        logger.debug(f"OpenAIEmbeddingClient initialized with model: {self.model}")

    def _get_embeddings(self):
        """OpenAIEmbeddingsインスタンスを取得（遅延初期化）"""
        if self._embeddings is None:
            try:
                from langchain_openai import OpenAIEmbeddings

                self._embeddings = OpenAIEmbeddings(model=self.model)
            except ImportError as e:
                raise EmbeddingError(
                    f"langchain-openai is required for OpenAI embeddings: {e}"
                )
        return self._embeddings

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        テキストリストをEmbeddingベクトルに変換

        Args:
            texts: 変換するテキストのリスト

        Returns:
            各テキストに対応するEmbeddingベクトルのリスト

        Raises:
            EmbeddingError: Embedding生成に失敗した場合
        """
        if not texts:
            return []

        try:
            embeddings = self._get_embeddings()
            result = await embeddings.aembed_documents(texts)
            logger.debug(f"Generated {len(result)} embeddings via OpenAI")
            return result
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise EmbeddingError(f"OpenAI embedding failed: {e}") from e

    async def embed_text(self, text: str) -> List[float]:
        """
        単一テキストをEmbeddingベクトルに変換

        Args:
            text: 変換するテキスト

        Returns:
            Embeddingベクトル

        Raises:
            EmbeddingError: Embedding生成に失敗した場合
        """
        try:
            embeddings = self._get_embeddings()
            result = await embeddings.aembed_query(text)
            logger.debug(f"Generated single embedding via OpenAI (dim={len(result)})")
            return result
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise EmbeddingError(f"OpenAI embedding failed: {e}") from e


def get_embedding_client(provider: Optional[str] = None) -> BaseEmbeddingClient:
    """
    Embeddingクライアントを取得するファクトリ関数

    Args:
        provider: プロバイダー名（"ollama" または "openai"）
                  省略時は設定ファイルから取得

    Returns:
        Embeddingクライアントインスタンス

    Raises:
        ValueError: 未対応のプロバイダーが指定された場合
    """
    config = get_config()
    # embedding.provider を優先、なければ llm.provider にフォールバック
    use_provider = provider or config.get("embedding.provider") or config.get("llm.provider", "ollama")

    logger.info(f"Creating embedding client: provider={use_provider}")

    if use_provider == "ollama":
        return OllamaEmbeddingClient()
    elif use_provider == "openai":
        return OpenAIEmbeddingClient()
    else:
        raise ValueError(
            f"Unsupported embedding provider: {use_provider}. "
            f"Supported providers: ollama, openai"
        )
