"""Tests for MarkdownConverter."""

import pytest

from minitools.scrapers.markdown_converter import MarkdownConverter


@pytest.fixture
def converter():
    return MarkdownConverter()


class TestMarkdownConverterHeadings:
    """見出し変換のテスト"""

    def test_h1(self, converter):
        """h1タグがMarkdownの#に変換される"""
        html = "<h1>Title</h1>"
        result = converter.convert(html)
        assert "# Title" in result

    def test_h2(self, converter):
        """h2タグがMarkdownの##に変換される"""
        html = "<h2>Subtitle</h2>"
        result = converter.convert(html)
        assert "## Subtitle" in result

    def test_h3(self, converter):
        """h3タグがMarkdownの###に変換される"""
        html = "<h3>Section</h3>"
        result = converter.convert(html)
        assert "### Section" in result


class TestMarkdownConverterCodeBlocks:
    """コードブロック変換のテスト"""

    def test_basic_code_block(self, converter):
        """基本的なコードブロックが変換される"""
        html = "<pre><code>print('hello')</code></pre>"
        result = converter.convert(html)
        assert "```" in result
        assert "print('hello')" in result

    def test_code_block_with_language(self, converter):
        """言語指定付きコードブロックが変換される"""
        html = '<pre><code class="language-python">def foo(): pass</code></pre>'
        result = converter.convert(html)
        assert "```python" in result
        assert "def foo(): pass" in result

    def test_code_block_lang_prefix(self, converter):
        """lang-プレフィックスの言語検出"""
        html = '<pre><code class="lang-javascript">const x = 1;</code></pre>'
        result = converter.convert(html)
        assert "```javascript" in result

    def test_code_block_with_br_tags(self, converter):
        """<br>タグを含むコードブロックで改行が保持される"""
        html = '<pre><code class="language-python">import instructor<br>from pydantic import BaseModel<br>from openai import OpenAI</code></pre>'
        result = converter.convert(html)
        assert "```python" in result
        assert "import instructor\nfrom pydantic" in result
        assert "BaseModel\nfrom openai" in result

    def test_code_block_with_br_tags_no_code_tag(self, converter):
        """<code>タグなしの<pre>要素で<br>タグが改行に変換される"""
        html = "<pre>line one<br>line two<br>line three</pre>"
        result = converter.convert(html)
        assert "line one\nline two\nline three" in result


class TestMarkdownConverterImages:
    """画像変換のテスト"""

    def test_basic_image(self, converter):
        """img要素がMarkdown画像に変換される"""
        html = '<img src="https://example.com/img.png" alt="test image">'
        result = converter.convert(html)
        assert "![test image](https://example.com/img.png)" in result

    def test_figure_with_caption(self, converter):
        """figure要素（画像+キャプション）が変換される"""
        html = """
        <figure>
            <img src="https://example.com/img.png" alt="diagram">
            <figcaption>Figure 1: Architecture</figcaption>
        </figure>
        """
        result = converter.convert(html)
        assert "![diagram](https://example.com/img.png)" in result
        assert "*Figure 1: Architecture*" in result

    def test_image_without_src(self, converter):
        """src属性がない画像は空文字列を返す"""
        html = '<img alt="no source">'
        result = converter.convert(html)
        assert "![" not in result


class TestMarkdownConverterLists:
    """リスト変換のテスト"""

    def test_unordered_list(self, converter):
        """順序なしリストが変換される"""
        html = "<ul><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul>"
        result = converter.convert(html)
        assert "- Item 1" in result
        assert "- Item 2" in result
        assert "- Item 3" in result

    def test_ordered_list(self, converter):
        """順序付きリストが変換される"""
        html = "<ol><li>First</li><li>Second</li><li>Third</li></ol>"
        result = converter.convert(html)
        assert "1. First" in result
        assert "2. Second" in result
        assert "3. Third" in result


class TestMarkdownConverterBlockquotes:
    """引用変換のテスト"""

    def test_basic_blockquote(self, converter):
        """引用要素が変換される"""
        html = "<blockquote>This is a quote</blockquote>"
        result = converter.convert(html)
        assert "> This is a quote" in result


class TestMarkdownConverterParagraphs:
    """段落変換のテスト"""

    def test_basic_paragraph(self, converter):
        """段落が変換される"""
        html = "<p>Hello World</p>"
        result = converter.convert(html)
        assert "Hello World" in result

    def test_paragraph_with_bold(self, converter):
        """太字を含む段落が変換される"""
        html = "<p>This is <strong>bold</strong> text</p>"
        result = converter.convert(html)
        assert "**bold**" in result

    def test_paragraph_with_italic(self, converter):
        """イタリックを含む段落が変換される"""
        html = "<p>This is <em>italic</em> text</p>"
        result = converter.convert(html)
        assert "*italic*" in result

    def test_paragraph_with_inline_code(self, converter):
        """インラインコードを含む段落が変換される"""
        html = "<p>Use <code>pip install</code> to install</p>"
        result = converter.convert(html)
        assert "`pip install`" in result

    def test_paragraph_with_link(self, converter):
        """リンクを含む段落が変換される"""
        html = '<p>Visit <a href="https://example.com">here</a></p>'
        result = converter.convert(html)
        assert "[here](https://example.com)" in result


class TestMarkdownConverterArticleExtraction:
    """Medium固有のHTML構造からの本文抽出テスト"""

    def test_article_tag_extraction(self, converter):
        """<article>タグから本文を抽出"""
        html = """
        <html>
        <body>
            <nav>Navigation</nav>
            <article>
                <section>
                    <h1>Article Title</h1>
                    <p>Article content here.</p>
                </section>
            </article>
            <footer>Footer</footer>
        </body>
        </html>
        """
        result = converter.convert(html)
        assert "# Article Title" in result
        assert "Article content here." in result
        assert "Navigation" not in result
        assert "Footer" not in result

    def test_fallback_to_body(self, converter):
        """articleタグがない場合はbodyにフォールバック"""
        html = """
        <html>
        <body>
            <h1>Title</h1>
            <p>Content</p>
        </body>
        </html>
        """
        result = converter.convert(html)
        assert "# Title" in result
        assert "Content" in result


class TestMarkdownConverterEdgeCases:
    """エッジケースのテスト"""

    def test_empty_html(self, converter):
        """空HTMLの処理"""
        assert converter.convert("") == ""
        assert converter.convert("   ") == ""

    def test_empty_elements(self, converter):
        """空の要素"""
        html = "<p></p><h1></h1>"
        result = converter.convert(html)
        assert result == "" or result.strip() == ""

    def test_horizontal_rule(self, converter):
        """水平線の処理"""
        html = "<hr>"
        result = converter.convert(html)
        assert "---" in result

    def test_complex_medium_article(self, converter):
        """Medium記事の複合的なHTML構造"""
        html = """
        <article>
            <section>
                <h1>Understanding LLMs</h1>
                <p>Large Language Models have <strong>revolutionized</strong> AI.</p>
                <h2>Architecture</h2>
                <p>The transformer architecture uses <code>attention</code> mechanisms.</p>
                <pre><code class="language-python">
import torch
model = torch.nn.Transformer()
</code></pre>
                <blockquote>Attention is all you need.</blockquote>
                <ul>
                    <li>Self-attention</li>
                    <li>Cross-attention</li>
                </ul>
                <figure>
                    <img src="https://example.com/arch.png" alt="Architecture">
                    <figcaption>Figure 1</figcaption>
                </figure>
            </section>
        </article>
        """
        result = converter.convert(html)
        assert "# Understanding LLMs" in result
        assert "**revolutionized**" in result
        assert "## Architecture" in result
        assert "`attention`" in result
        assert "```python" in result
        assert "import torch" in result
        assert "> Attention is all you need." in result
        assert "- Self-attention" in result
        assert "![Architecture](https://example.com/arch.png)" in result
        assert "*Figure 1*" in result


class TestMarkdownConverterRichText:
    """_get_rich_textの未カバーパターンのテスト"""

    def test_paragraph_with_br(self, converter):
        """brタグが改行に変換される"""
        html = "<p>Line one<br>Line two</p>"
        result = converter.convert(html)
        assert "Line one\nLine two" in result

    def test_paragraph_with_link_no_href(self, converter):
        """href属性がないリンクはテキストのみ"""
        html = "<p>Click <a>here</a> for more</p>"
        result = converter.convert(html)
        assert "here" in result
        assert "[" not in result

    def test_paragraph_with_inline_image(self, converter):
        """段落内のimg要素がMarkdown画像に変換される"""
        html = '<p>See diagram <img src="https://example.com/d.png" alt="fig"></p>'
        result = converter.convert(html)
        assert "![fig](https://example.com/d.png)" in result

    def test_paragraph_with_unknown_tag(self, converter):
        """未知のタグはテキストとして抽出される"""
        html = "<p>Normal <span>span text</span> end</p>"
        result = converter.convert(html)
        assert "span text" in result

    def test_paragraph_with_b_tag(self, converter):
        """bタグが太字に変換される"""
        html = "<p>This is <b>bold</b> text</p>"
        result = converter.convert(html)
        assert "**bold**" in result

    def test_paragraph_with_i_tag(self, converter):
        """iタグがイタリックに変換される"""
        html = "<p>This is <i>italic</i> text</p>"
        result = converter.convert(html)
        assert "*italic*" in result


class TestMarkdownConverterContainer:
    """_process_containerのテスト"""

    def test_div_with_mixed_content(self, converter):
        """div内のテキストとタグが処理される"""
        html = "<div>Text node<p>Paragraph</p></div>"
        result = converter.convert(html)
        assert "Text node" in result
        assert "Paragraph" in result

    def test_nested_sections(self, converter):
        """ネストされたsectionが再帰的に処理される"""
        html = """
        <div>
            <section>
                <h2>Inner Heading</h2>
                <p>Inner content</p>
            </section>
        </div>
        """
        result = converter.convert(html)
        assert "## Inner Heading" in result
        assert "Inner content" in result

    def test_div_with_navigable_string(self, converter):
        """div内のNavigableStringが処理される"""
        html = "<div>Just text</div>"
        result = converter.convert(html)
        assert "Just text" in result


class TestMarkdownConverterUncoveredPaths:
    """未カバー分岐のテスト"""

    def test_navigable_string_in_article_body(self, converter):
        """記事本文直下のNavigableStringテキストが抽出される（43行目）"""
        html = """
        <article>
            <section>
                Bare text node
                <p>Paragraph</p>
            </section>
        </article>
        """
        result = converter.convert(html)
        assert "Bare text node" in result
        assert "Paragraph" in result

    def test_article_without_sections(self, converter):
        """articleタグ内にsectionがない場合、article自体を本文とする（73行目）"""
        html = """
        <article>
            <h1>Title</h1>
            <p>Content without section</p>
        </article>
        """
        result = converter.convert(html)
        assert "# Title" in result
        assert "Content without section" in result

    def test_unknown_element_text_extraction(self, converter):
        """未知のトップレベル要素からテキストが抽出される（115-116行目）"""
        html = """
        <article>
            <section>
                <span>Span top-level text</span>
            </section>
        </article>
        """
        result = converter.convert(html)
        assert "Span top-level text" in result

    def test_unknown_element_empty(self, converter):
        """空の未知要素は空文字列を返す"""
        html = """
        <article>
            <section>
                <span></span>
                <p>After empty span</p>
            </section>
        </article>
        """
        result = converter.convert(html)
        assert "After empty span" in result

    def test_pre_without_code_tag(self, converter):
        """<code>タグなしの<pre>要素がコードブロックに変換される（134-135行目）"""
        html = "<pre>plain preformatted text</pre>"
        result = converter.convert(html)
        assert "```" in result
        assert "plain preformatted text" in result

    def test_code_class_as_string(self, converter):
        """class属性が文字列型の場合でも言語検出される（150行目）"""
        # BeautifulSoupは通常listを返すが、文字列の場合もハンドルする
        html = '<pre><code class="language-ruby">puts "hello"</code></pre>'
        result = converter.convert(html)
        assert "```ruby" in result
        assert 'puts "hello"' in result

    def test_parent_element_language_detection_list(self, converter):
        """親要素（pre）のclass属性リストから言語検出（163行目）"""
        html = '<pre class="language-go"><code>fmt.Println("hi")</code></pre>'
        result = converter.convert(html)
        assert "```go" in result

    def test_parent_element_language_detection_string(self, converter):
        """親要素のclass属性が文字列型の場合の言語検出（165, 167-169行目）"""
        html = '<pre class="lang-scala"><code>val x = 1</code></pre>'
        result = converter.convert(html)
        assert "```scala" in result

    def test_empty_blockquote(self, converter):
        """空の引用要素は空文字列を返す（222行目）"""
        html = "<blockquote></blockquote>"
        result = converter.convert(html)
        # 空blockquoteは出力なし
        assert result == "" or ">" not in result
