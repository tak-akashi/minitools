"""
Duplicate article detector using embedding similarity.
"""

import math
from typing import Any, Dict, List, Tuple

from minitools.llm.embeddings import BaseEmbeddingClient, EmbeddingError
from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class UnionFind:
    """Union-Findデータ構造（クラスタリング用）"""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

    def get_groups(self) -> Dict[int, List[int]]:
        """各グループのメンバーを返す"""
        groups: Dict[int, List[int]] = {}
        for i in range(len(self.parent)):
            root = self.find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)
        return groups


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    2つのベクトル間のコサイン類似度を計算

    Args:
        vec1: ベクトル1
        vec2: ベクトル2

    Returns:
        コサイン類似度（-1.0〜1.0）
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimensions must match: {len(vec1)} vs {len(vec2)}")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


class DuplicateDetector:
    """類似記事検出クラス"""

    def __init__(
        self,
        embedding_client: BaseEmbeddingClient,
        similarity_threshold: float = 0.85,
    ):
        """
        Args:
            embedding_client: Embeddingクライアント
            similarity_threshold: 類似度閾値（デフォルト: 0.85）
        """
        self.embedding_client = embedding_client
        self.similarity_threshold = similarity_threshold
        logger.info(
            f"DuplicateDetector initialized (threshold={similarity_threshold})"
        )

    def _prepare_text(self, article: Dict[str, Any]) -> str:
        """
        記事からEmbedding対象のテキストを生成

        Args:
            article: 記事データ

        Returns:
            タイトル + 要約（先頭200文字）
        """
        title = article.get("title", article.get("original_title", ""))
        summary = article.get("summary", article.get("snippet", ""))

        # タイトル + 要約の先頭200文字
        text = f"{title}\n{summary[:200]}" if summary else title
        return text.strip()

    async def _compute_embeddings(
        self, articles: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
        """
        記事リストのEmbeddingを計算

        Args:
            articles: 記事リスト

        Returns:
            (有効な記事リスト, Embeddingベクトルリスト)のタプル
        """
        texts = []
        valid_articles = []

        for article in articles:
            text = self._prepare_text(article)
            if text:
                texts.append(text)
                valid_articles.append(article)

        if not texts:
            return [], []

        logger.info(f"Computing embeddings for {len(texts)} articles...")

        try:
            embeddings = await self.embedding_client.embed_texts(texts)
            logger.info(f"Generated {len(embeddings)} embeddings")
            return valid_articles, embeddings
        except EmbeddingError as e:
            logger.error(f"Failed to compute embeddings: {e}")
            raise

    def _cluster_by_similarity(
        self, embeddings: List[List[float]]
    ) -> Dict[int, List[int]]:
        """
        Embedding類似度でクラスタリング

        Args:
            embeddings: Embeddingベクトルリスト

        Returns:
            クラスタID -> 記事インデックスリストの辞書
        """
        n = len(embeddings)
        if n == 0:
            return {}

        uf = UnionFind(n)

        # 全ペアの類似度を計算してクラスタリング
        for i in range(n):
            for j in range(i + 1, n):
                sim = cosine_similarity(embeddings[i], embeddings[j])
                if sim >= self.similarity_threshold:
                    uf.union(i, j)
                    logger.debug(f"Merged articles {i} and {j} (similarity={sim:.3f})")

        return uf.get_groups()

    async def detect_duplicates(
        self, articles: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        類似記事をグループ化して返す

        Args:
            articles: 記事データのリスト

        Returns:
            類似記事グループのリスト（各グループは記事リスト）
        """
        if not articles:
            return []

        # Embeddingを計算
        valid_articles, embeddings = await self._compute_embeddings(articles)

        if not embeddings:
            return [[a] for a in articles]

        # 類似度でクラスタリング
        clusters = self._cluster_by_similarity(embeddings)

        # クラスタを記事グループに変換
        groups = []
        for indices in clusters.values():
            group = [valid_articles[i] for i in indices]
            groups.append(group)

        # 重複グループの数をログ出力
        duplicate_groups = [g for g in groups if len(g) > 1]
        if duplicate_groups:
            logger.info(
                f"Detected {len(duplicate_groups)} duplicate groups "
                f"(total {sum(len(g) for g in duplicate_groups)} articles)"
            )
            for i, group in enumerate(duplicate_groups, 1):
                titles = [
                    g.get("title", g.get("original_title", "N/A"))[:40]
                    for g in group
                ]
                logger.info(f"  Group {i}: {titles}")

        return groups

    def select_representatives(
        self,
        groups: List[List[Dict[str, Any]]],
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        各グループから代表記事を選出し、上位N件を返す

        Args:
            groups: 類似記事グループのリスト
            top_n: 取得する記事数（デフォルト: 20）

        Returns:
            代表記事のリスト（スコア降順）
        """
        representatives = []

        for group in groups:
            if not group:
                continue

            # グループ内で最高スコアの記事を選出
            best = max(
                group,
                key=lambda a: a.get("importance_score", 0),
            )
            best["duplicate_count"] = len(group)
            representatives.append(best)

        # スコア降順でソート
        representatives.sort(
            key=lambda x: x.get("importance_score", 0),
            reverse=True,
        )

        selected = representatives[:top_n]
        logger.info(
            f"Selected {len(selected)} representative articles from "
            f"{len(groups)} groups"
        )

        return selected


async def deduplicate_articles(
    articles: List[Dict[str, Any]],
    embedding_client: BaseEmbeddingClient,
    similarity_threshold: float = 0.85,
    buffer_ratio: float = 2.5,
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """
    記事リストから重複を除去して上位N件を返す

    Args:
        articles: 記事データのリスト（importance_score付き）
        embedding_client: Embeddingクライアント
        similarity_threshold: 類似度閾値（デフォルト: 0.85）
        buffer_ratio: 候補記事の倍率（デフォルト: 2.5）
        top_n: 最終的に取得する記事数（デフォルト: 20）

    Returns:
        重複除去済みの上位N件記事リスト
    """
    if not articles:
        return []

    # バッファ込みの候補数を計算
    buffer_n = int(top_n * buffer_ratio)

    # スコア上位をバッファとして選出
    sorted_articles = sorted(
        articles,
        key=lambda x: x.get("importance_score", 0),
        reverse=True,
    )
    candidates = sorted_articles[:buffer_n]

    logger.info(
        f"Deduplication: {len(articles)} articles -> "
        f"top {len(candidates)} candidates (buffer={buffer_ratio}x)"
    )

    # 重複検出と代表記事選出
    detector = DuplicateDetector(
        embedding_client=embedding_client,
        similarity_threshold=similarity_threshold,
    )

    groups = await detector.detect_duplicates(candidates)
    result = detector.select_representatives(groups, top_n)

    return result
