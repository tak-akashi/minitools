"""
HTML to structured Markdown converter for Medium articles.
"""

import re
from typing import Any, List, Optional

from bs4 import BeautifulSoup, Tag, NavigableString

from minitools.utils.logger import get_logger

logger = get_logger(__name__)


class MarkdownConverter:
    """Medium記事のHTMLを構造化Markdownに変換するクラス"""

    def convert(self, html: str) -> str:
        """
        HTML文字列を構造化Markdownに変換する

        Args:
            html: Medium記事のHTML文字列

        Returns:
            構造化されたMarkdown文字列
        """
        if not html or not html.strip():
            return ""

        soup = BeautifulSoup(html, "html.parser")
        article_body = self._extract_article_body(soup)

        if article_body is None:
            logger.warning("Article body not found, using full HTML")
            article_body = soup

        lines: List[str] = []
        for element in article_body.children:
            if isinstance(element, NavigableString):
                text = element.strip()
                if text:
                    lines.append(text)
                continue
            if isinstance(element, Tag):
                result = self._process_element(element)
                if result:
                    lines.append(result)

        markdown = "\n\n".join(lines)
        # 連続する空行を2行に正規化
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown.strip()

    def _extract_article_body(self, soup: BeautifulSoup) -> Optional[Tag]:
        """
        Medium固有のHTML構造から記事本文を抽出する

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            記事本文のTagオブジェクト、見つからない場合はNone
        """
        # Medium記事の典型的な構造: <article> タグ内
        article = soup.find("article")
        if article and isinstance(article, Tag):
            # article内のsectionを探す
            sections = article.find_all("section")
            if sections:
                # 最後のsection（通常本文が含まれる）
                return sections[-1]
            return article

        # articleタグがない場合はbodyを使用
        body = soup.find("body")
        if body and isinstance(body, Tag):
            return body

        return None

    def _process_element(self, element: Tag) -> str:
        """
        HTML要素をMarkdownに変換する

        Args:
            element: HTML要素

        Returns:
            Markdown文字列
        """
        tag_name = element.name

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return self._process_heading(element)
        elif tag_name == "pre":
            return self._process_code_block(element)
        elif tag_name == "blockquote":
            return self._process_blockquote(element)
        elif tag_name in ("ul", "ol"):
            return self._process_list(element)
        elif tag_name == "figure":
            return self._process_figure(element)
        elif tag_name == "img":
            return self._process_image(element)
        elif tag_name == "p":
            return self._process_paragraph(element)
        elif tag_name in ("div", "section"):
            # div/sectionは再帰的に処理
            return self._process_container(element)
        elif tag_name == "hr":
            return "---"
        else:
            # 未知の要素はテキストを抽出
            text = self._get_text(element)
            return text if text else ""

    def _process_heading(self, element: Tag) -> str:
        """見出し要素をMarkdownに変換"""
        level = int(element.name[1])
        text = self._get_text(element)
        if not text:
            return ""
        prefix = "#" * level
        return f"{prefix} {text}"

    def _process_code_block(self, element: Tag) -> str:
        """コードブロック要素をMarkdownに変換"""
        code_tag = element.find("code")
        if code_tag and isinstance(code_tag, Tag):
            code_text = code_tag.get_text()
            language = self._detect_language(code_tag)
        else:
            code_text = element.get_text()
            language = ""

        # 末尾の改行を除去
        code_text = code_text.rstrip("\n")

        return f"```{language}\n{code_text}\n```"

    def _detect_language(self, code_tag: Tag) -> str:
        """コードブロックのプログラミング言語を検出"""
        # class属性から言語を推定
        raw_classes: Any = code_tag.get("class")
        classes: List[str] = []
        if isinstance(raw_classes, list):
            classes = [str(c) for c in raw_classes]
        elif isinstance(raw_classes, str):
            classes = [raw_classes]

        for cls in classes:
            match = re.match(r"(?:language|lang)-(\w+)", cls)
            if match:
                return match.group(1)

        # 親要素のclassも確認
        parent = code_tag.parent
        if parent and isinstance(parent, Tag):
            raw_parent: Any = parent.get("class")
            parent_classes: List[str] = []
            if isinstance(raw_parent, list):
                parent_classes = [str(c) for c in raw_parent]
            elif isinstance(raw_parent, str):
                parent_classes = [raw_parent]
            for cls in parent_classes:
                match = re.match(r"(?:language|lang)-(\w+)", cls)
                if match:
                    return match.group(1)

        return ""

    def _process_image(self, element: Tag) -> str:
        """画像要素をMarkdownに変換"""
        src = element.get("src", "")
        alt = element.get("alt", "")

        if not src:
            return ""

        return f"![{alt}]({src})"

    def _process_figure(self, element: Tag) -> str:
        """figure要素（画像+キャプション）をMarkdownに変換"""
        parts: List[str] = []

        # 画像を抽出
        img = element.find("img")
        if img and isinstance(img, Tag):
            img_md = self._process_image(img)
            if img_md:
                parts.append(img_md)

        # キャプションを抽出
        figcaption = element.find("figcaption")
        if figcaption and isinstance(figcaption, Tag):
            caption = self._get_text(figcaption)
            if caption:
                parts.append(f"*{caption}*")

        return "\n\n".join(parts)

    def _process_list(self, element: Tag) -> str:
        """リスト要素をMarkdownに変換"""
        is_ordered = element.name == "ol"
        items: List[str] = []

        for i, li in enumerate(element.find_all("li", recursive=False)):
            text = self._get_text(li)
            if text:
                if is_ordered:
                    items.append(f"{i + 1}. {text}")
                else:
                    items.append(f"- {text}")

        return "\n".join(items)

    def _process_blockquote(self, element: Tag) -> str:
        """引用要素をMarkdownに変換"""
        text = self._get_text(element)
        if not text:
            return ""

        # 各行に > を追加
        lines = text.split("\n")
        quoted_lines = [f"> {line}" for line in lines]
        return "\n".join(quoted_lines)

    def _process_paragraph(self, element: Tag) -> str:
        """段落要素をMarkdownに変換（インライン要素を保持）"""
        return self._get_rich_text(element)

    def _process_container(self, element: Tag) -> str:
        """div/section要素を再帰的に処理"""
        parts: List[str] = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = child.strip()
                if text:
                    parts.append(text)
            elif isinstance(child, Tag):
                result = self._process_element(child)
                if result:
                    parts.append(result)
        return "\n\n".join(parts)

    def _get_text(self, element: Tag) -> str:
        """要素からテキストを取得（前後の空白を除去）"""
        text = element.get_text(separator=" ", strip=True)
        # 連続する空白を1つに正規化
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _get_rich_text(self, element: Tag) -> str:
        """要素からリッチテキスト（太字・イタリック・リンク等）を取得"""
        parts: List[str] = []

        for child in element.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name == "strong" or child.name == "b":
                    parts.append(f"**{child.get_text()}**")
                elif child.name == "em" or child.name == "i":
                    parts.append(f"*{child.get_text()}*")
                elif child.name == "code":
                    parts.append(f"`{child.get_text()}`")
                elif child.name == "a":
                    href = child.get("href", "")
                    text = child.get_text()
                    if href:
                        parts.append(f"[{text}]({href})")
                    else:
                        parts.append(text)
                elif child.name == "br":
                    parts.append("\n")
                elif child.name == "img":
                    img_md = self._process_image(child)
                    if img_md:
                        parts.append(img_md)
                else:
                    parts.append(child.get_text())

        result = "".join(parts).strip()
        return result
