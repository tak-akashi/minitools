"""Tests for NotionBlockBuilder."""

import pytest

from minitools.publishers.notion_block_builder import NotionBlockBuilder


@pytest.fixture
def builder():
    return NotionBlockBuilder()


class TestNotionBlockBuilderDivider:
    """区切り線ブロックのテスト"""

    def test_starts_with_divider(self, builder):
        """最初のブロックがdividerであること"""
        blocks = builder.build_blocks("Hello")
        assert blocks[0]["type"] == "divider"

    def test_divider_structure(self, builder):
        """dividerブロックの構造"""
        blocks = builder.build_blocks("Hello")
        divider = blocks[0]
        assert divider["object"] == "block"
        assert divider["type"] == "divider"
        assert "divider" in divider


class TestNotionBlockBuilderHeadings:
    """見出しブロックのテスト"""

    def test_heading_1(self, builder):
        """heading_1ブロックの生成"""
        blocks = builder.build_blocks("# Title")
        heading = blocks[1]  # blocks[0] is divider
        assert heading["type"] == "heading_1"
        assert heading["heading_1"]["rich_text"][0]["text"]["content"] == "Title"

    def test_heading_2(self, builder):
        """heading_2ブロックの生成"""
        blocks = builder.build_blocks("## Subtitle")
        heading = blocks[1]
        assert heading["type"] == "heading_2"
        assert heading["heading_2"]["rich_text"][0]["text"]["content"] == "Subtitle"

    def test_heading_3(self, builder):
        """heading_3ブロックの生成"""
        blocks = builder.build_blocks("### Section")
        heading = blocks[1]
        assert heading["type"] == "heading_3"
        assert heading["heading_3"]["rich_text"][0]["text"]["content"] == "Section"


class TestNotionBlockBuilderParagraphs:
    """段落ブロックのテスト"""

    def test_basic_paragraph(self, builder):
        """段落ブロックの生成"""
        blocks = builder.build_blocks("Hello World")
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert para["paragraph"]["rich_text"][0]["text"]["content"] == "Hello World"

    def test_long_text_split(self, builder):
        """2000文字超のテキストが分割される"""
        long_text = "A" * 3000
        blocks = builder.build_blocks(long_text)
        para = blocks[1]
        rich_text = para["paragraph"]["rich_text"]
        assert len(rich_text) == 2
        assert len(rich_text[0]["text"]["content"]) == 2000
        assert len(rich_text[1]["text"]["content"]) == 1000


class TestNotionBlockBuilderCodeBlocks:
    """コードブロックのテスト"""

    def test_basic_code_block(self, builder):
        """コードブロックの生成"""
        md = "```python\nprint('hello')\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["type"] == "code"
        assert code["code"]["language"] == "python"
        assert code["code"]["rich_text"][0]["text"]["content"] == "print('hello')"

    def test_code_block_no_language(self, builder):
        """言語指定なしのコードブロック"""
        md = "```\nsome code\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["type"] == "code"
        assert code["code"]["language"] == "plain text"

    def test_code_block_language_mapping(self, builder):
        """言語名のマッピング"""
        md = "```js\nconst x = 1;\n```"
        blocks = builder.build_blocks(md)
        code = blocks[1]
        assert code["code"]["language"] == "javascript"


class TestNotionBlockBuilderImages:
    """画像ブロックのテスト"""

    def test_basic_image(self, builder):
        """画像ブロックの生成"""
        md = "![alt text](https://example.com/img.png)"
        blocks = builder.build_blocks(md)
        img = blocks[1]
        assert img["type"] == "image"
        assert img["image"]["type"] == "external"
        assert img["image"]["external"]["url"] == "https://example.com/img.png"


class TestNotionBlockBuilderLists:
    """リストブロックのテスト"""

    def test_bulleted_list(self, builder):
        """箇条書きリストの生成"""
        md = "- Item 1\n- Item 2"
        blocks = builder.build_blocks(md)
        assert blocks[1]["type"] == "bulleted_list_item"
        assert blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "Item 1"
        assert blocks[2]["type"] == "bulleted_list_item"

    def test_numbered_list(self, builder):
        """番号付きリストの生成"""
        md = "1. First\n2. Second"
        blocks = builder.build_blocks(md)
        assert blocks[1]["type"] == "numbered_list_item"
        assert blocks[1]["numbered_list_item"]["rich_text"][0]["text"]["content"] == "First"
        assert blocks[2]["type"] == "numbered_list_item"


class TestNotionBlockBuilderQuotes:
    """引用ブロックのテスト"""

    def test_basic_quote(self, builder):
        """引用ブロックの生成"""
        md = "> This is a quote"
        blocks = builder.build_blocks(md)
        quote = blocks[1]
        assert quote["type"] == "quote"
        assert quote["quote"]["rich_text"][0]["text"]["content"] == "This is a quote"

    def test_multiline_quote(self, builder):
        """複数行引用の結合"""
        md = "> Line 1\n> Line 2"
        blocks = builder.build_blocks(md)
        quote = blocks[1]
        assert quote["type"] == "quote"
        assert "Line 1\nLine 2" in quote["quote"]["rich_text"][0]["text"]["content"]


class TestNotionBlockBuilderHorizontalRules:
    """水平線ブロックのテスト"""

    def test_horizontal_rule_dashes(self, builder):
        """---が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n---\n\nmore text")
        types = [b["type"] for b in blocks]
        # divider(先頭) + paragraph + divider(---) + paragraph
        assert types.count("divider") == 2

    def test_horizontal_rule_asterisks(self, builder):
        """***が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n***\n\nmore text")
        types = [b["type"] for b in blocks]
        assert types.count("divider") == 2

    def test_horizontal_rule_underscores(self, builder):
        """___が水平線（divider）に変換される"""
        blocks = builder.build_blocks("text\n\n___\n\nmore text")
        types = [b["type"] for b in blocks]
        assert types.count("divider") == 2


class TestNotionBlockBuilderItalicLines:
    """イタリック行（キャプション等）のテスト"""

    def test_italic_line(self, builder):
        """*text*がイタリック段落に変換される"""
        blocks = builder.build_blocks("*Caption text*")
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert para["paragraph"]["rich_text"][0]["text"]["content"] == "*Caption text*"

    def test_italic_line_with_spaces(self, builder):
        """前後にスペースのあるイタリック行"""
        blocks = builder.build_blocks("  *Figure 1: Diagram*  ")
        para = blocks[1]
        assert para["type"] == "paragraph"
        assert "*Figure 1: Diagram*" in para["paragraph"]["rich_text"][0]["text"]["content"]


class TestNotionBlockBuilderRichText:
    """_build_rich_textのテスト"""

    def test_empty_text_returns_empty_content(self, builder):
        """空テキストでも空contentのrich_textを返す"""
        rich_text = builder._build_rich_text("")
        assert len(rich_text) == 1
        assert rich_text[0]["type"] == "text"
        assert rich_text[0]["text"]["content"] == ""

    def test_none_text_returns_empty_content(self, builder):
        """Noneテキストでも空contentのrich_textを返す"""
        rich_text = builder._build_rich_text(None)
        assert len(rich_text) == 1
        assert rich_text[0]["text"]["content"] == ""


class TestNotionBlockBuilderComplex:
    """複合的なMarkdownのテスト"""

    def test_complex_markdown(self, builder):
        """複合的なMarkdownからのブロック列生成"""
        md = """# Title

This is a paragraph.

## Section 1

- Item A
- Item B

```python
print("hello")
```

> A quote here

1. First
2. Second

![img](https://example.com/img.png)"""

        blocks = builder.build_blocks(md)
        # divider + heading_1 + paragraph + heading_2 + 2 bullets + code + quote + 2 numbered + image = 11
        types = [b["type"] for b in blocks]
        assert types[0] == "divider"
        assert "heading_1" in types
        assert "heading_2" in types
        assert "paragraph" in types
        assert "bulleted_list_item" in types
        assert "code" in types
        assert "quote" in types
        assert "numbered_list_item" in types
        assert "image" in types

    def test_empty_markdown(self, builder):
        """空Markdownの処理"""
        assert builder.build_blocks("") == []
        assert builder.build_blocks("   ") == []
