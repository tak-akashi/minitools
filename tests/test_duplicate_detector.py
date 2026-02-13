"""Tests for DuplicateDetector and related functions."""

import pytest

from minitools.processors.duplicate_detector import (
    DuplicateDetector,
    UnionFind,
    cosine_similarity,
    deduplicate_articles,
)


class TestUnionFind:
    """Union-Findデータ構造のテスト"""

    def test_initial_state(self):
        """初期状態では各要素が独立したグループ"""
        uf = UnionFind(5)
        groups = uf.get_groups()
        assert len(groups) == 5

    def test_union_two_elements(self):
        """2要素の結合テスト"""
        uf = UnionFind(5)
        uf.union(0, 1)
        groups = uf.get_groups()
        assert len(groups) == 4

    def test_union_chain(self):
        """連鎖的な結合テスト"""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(1, 2)
        groups = uf.get_groups()
        # 0, 1, 2が1グループ、3, 4が独立
        assert len(groups) == 3

    def test_find_with_path_compression(self):
        """経路圧縮が正しく動作することを確認"""
        uf = UnionFind(5)
        uf.union(0, 1)
        uf.union(1, 2)
        uf.union(2, 3)

        # 全要素が同じルートを持つはず
        root = uf.find(0)
        assert uf.find(1) == root
        assert uf.find(2) == root
        assert uf.find(3) == root

    def test_get_groups(self):
        """グループ取得テスト"""
        uf = UnionFind(6)
        uf.union(0, 1)
        uf.union(2, 3)
        uf.union(3, 4)

        groups = uf.get_groups()
        assert len(groups) == 3  # {0,1}, {2,3,4}, {5}

        # グループサイズを確認
        group_sizes = sorted([len(g) for g in groups.values()])
        assert group_sizes == [1, 2, 3]


class TestCosineSimilarity:
    """コサイン類似度計算のテスト"""

    def test_identical_vectors(self):
        """同一ベクトルの類似度は1.0"""
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0, rel=1e-6)

    def test_orthogonal_vectors(self):
        """直交ベクトルの類似度は0.0"""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(0.0, rel=1e-6)

    def test_opposite_vectors(self):
        """反対ベクトルの類似度は-1.0"""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        assert cosine_similarity(vec1, vec2) == pytest.approx(-1.0, rel=1e-6)

    def test_similar_vectors(self):
        """類似ベクトルの類似度テスト"""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.1, 2.1, 3.1]
        sim = cosine_similarity(vec1, vec2)
        assert sim > 0.99  # 非常に類似している

    def test_zero_vector(self):
        """ゼロベクトルの場合は0.0を返す"""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec1, vec2) == 0.0

    def test_dimension_mismatch_raises_error(self):
        """次元が異なる場合はエラー"""
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        with pytest.raises(ValueError):
            cosine_similarity(vec1, vec2)


class TestDuplicateDetector:
    """DuplicateDetectorのテスト"""

    @pytest.mark.asyncio
    async def test_detect_duplicates_no_duplicates(self, mock_embedding_client):
        """重複がない場合のテスト"""
        detector = DuplicateDetector(
            embedding_client=mock_embedding_client,
            similarity_threshold=0.95,  # 高い閾値
        )
        articles = [
            {"title": "Article A", "summary": "Unique content about topic A"},
            {"title": "Article B", "summary": "Different content about topic B"},
            {"title": "Article C", "summary": "Completely separate topic C"},
        ]

        groups = await detector.detect_duplicates(articles)

        # 各記事が別グループになるはず（閾値が高いため）
        assert len(groups) == 3

    @pytest.mark.asyncio
    async def test_detect_duplicates_empty_list(self, mock_embedding_client):
        """空リストの場合のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        groups = await detector.detect_duplicates([])

        assert groups == []

    @pytest.mark.asyncio
    async def test_prepare_text(self, mock_embedding_client):
        """テキスト準備のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        article = {"title": "Test Title", "summary": "Test Summary" * 100}
        text = detector._prepare_text(article)

        # タイトル + 改行 + 要約（200文字制限）
        assert text.startswith("Test Title\n")
        assert len(text.split("\n")[1]) <= 200

    @pytest.mark.asyncio
    async def test_prepare_text_alternative_keys(self, mock_embedding_client):
        """代替キー（original_title, snippet）のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        article = {"original_title": "Alt Title", "snippet": "Alt Snippet"}
        text = detector._prepare_text(article)

        assert "Alt Title" in text
        assert "Alt Snippet" in text

    @pytest.mark.asyncio
    async def test_prepare_text_title_only(self, mock_embedding_client):
        """タイトルのみの場合のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        article = {"title": "Only Title"}
        text = detector._prepare_text(article)

        assert text == "Only Title"

    @pytest.mark.asyncio
    async def test_select_representatives_basic(self, mock_embedding_client):
        """代表記事選出の基本テスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        groups = [
            [
                {"title": "A1", "importance_score": 8.0},
                {"title": "A2", "importance_score": 6.0},
            ],
            [
                {"title": "B1", "importance_score": 9.0},
            ],
            [
                {"title": "C1", "importance_score": 5.0},
                {"title": "C2", "importance_score": 7.0},
                {"title": "C3", "importance_score": 4.0},
            ],
        ]

        result = detector.select_representatives(groups, top_n=3)

        assert len(result) == 3
        # スコア降順: B1(9.0), A1(8.0), C2(7.0)
        assert result[0]["title"] == "B1"
        assert result[1]["title"] == "A1"
        assert result[2]["title"] == "C2"

    @pytest.mark.asyncio
    async def test_select_representatives_with_duplicate_count(
        self, mock_embedding_client
    ):
        """代表記事にduplicate_countが付与されることを確認"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        groups = [
            [
                {"title": "A1", "importance_score": 8.0},
                {"title": "A2", "importance_score": 6.0},
            ],
        ]

        result = detector.select_representatives(groups, top_n=1)

        assert len(result) == 1
        assert result[0]["duplicate_count"] == 2

    @pytest.mark.asyncio
    async def test_select_representatives_top_n_limit(self, mock_embedding_client):
        """top_n制限のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        groups = [
            [{"title": f"Article {i}", "importance_score": float(i)}] for i in range(10)
        ]

        result = detector.select_representatives(groups, top_n=3)

        assert len(result) == 3
        # 上位3件（スコア9, 8, 7）
        assert result[0]["importance_score"] == 9.0

    @pytest.mark.asyncio
    async def test_select_representatives_empty_groups(self, mock_embedding_client):
        """空グループがある場合のテスト"""
        detector = DuplicateDetector(embedding_client=mock_embedding_client)

        groups = [
            [],
            [{"title": "A", "importance_score": 5.0}],
            [],
        ]

        result = detector.select_representatives(groups, top_n=5)

        assert len(result) == 1


class TestDeduplicateArticles:
    """deduplicate_articles関数のテスト"""

    @pytest.mark.asyncio
    async def test_deduplicate_articles_basic(self, mock_embedding_client):
        """基本的な重複除去テスト"""
        articles = [
            {
                "title": f"Article {i}",
                "summary": f"Summary {i}",
                "importance_score": float(10 - i),
            }
            for i in range(10)
        ]

        result = await deduplicate_articles(
            articles=articles,
            embedding_client=mock_embedding_client,
            similarity_threshold=0.95,  # 高い閾値（重複検出されにくい）
            buffer_ratio=2.0,
            top_n=5,
        )

        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_deduplicate_articles_empty_list(self, mock_embedding_client):
        """空リストの場合のテスト"""
        result = await deduplicate_articles(
            articles=[],
            embedding_client=mock_embedding_client,
            top_n=5,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_deduplicate_articles_buffer_ratio(self, mock_embedding_client):
        """バッファ倍率のテスト"""
        articles = [
            {
                "title": f"Article {i}",
                "summary": f"Summary {i}",
                "importance_score": float(100 - i),
            }
            for i in range(100)
        ]

        # buffer_ratio=2.5, top_n=10 の場合、25件が候補として選出される
        result = await deduplicate_articles(
            articles=articles,
            embedding_client=mock_embedding_client,
            similarity_threshold=0.99,  # 非常に高い閾値
            buffer_ratio=2.5,
            top_n=10,
        )

        assert len(result) <= 10

    @pytest.mark.asyncio
    async def test_deduplicate_articles_preserves_order(self, mock_embedding_client):
        """スコア順が保持されることを確認"""
        articles = [
            {"title": "Low score", "summary": "Low", "importance_score": 1.0},
            {"title": "High score", "summary": "High", "importance_score": 10.0},
            {"title": "Mid score", "summary": "Mid", "importance_score": 5.0},
        ]

        result = await deduplicate_articles(
            articles=articles,
            embedding_client=mock_embedding_client,
            similarity_threshold=0.99,
            top_n=3,
        )

        # スコア降順でソートされている
        scores = [a["importance_score"] for a in result]
        assert scores == sorted(scores, reverse=True)
