"""
buildBlog.py — Converts markdown files in posts/ into styled HTML blog pages
and updates the blog index (index.html).

Usage:
    python buildBlog.py            Build all posts and rebuild index
    python buildBlog.py --new      Open posts/ folder to add a new markdown file

Markdown files go in:  posts/
Each .md file must start with a YAML-style front-matter block:
    ---
    title: My Post Title
    date: 2026-10-28
    description: A short description for SEO.
    ---

    Your markdown content here...

Images referenced in markdown (e.g. ![alt](my_image.jpg)) should be placed
in the same posts/ folder or a subfolder. They will be copied alongside the
generated HTML into posts/ (paths are kept relative).
"""

import os
import re
import sys
import shutil
import html as html_module

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(SCRIPT_DIR, "posts")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "blog_template.html")
INDEX_PATH = os.path.join(SCRIPT_DIR, "index.html")


# ---------------------------------------------------------------------------
#  Front-matter parser
# ---------------------------------------------------------------------------
def parse_frontmatter(text):
    """Return (metadata_dict, body_markdown)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        # No front-matter — derive title from first heading
        title_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Untitled"
        return {"title": title, "date": "", "description": ""}, text

    raw = match.group(1)
    body = text[match.end():]
    meta = {}
    for line in raw.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip().lower()] = val.strip()
    meta.setdefault("title", "Untitled")
    meta.setdefault("date", "")
    meta.setdefault("description", "")
    return meta, body


# ---------------------------------------------------------------------------
#  Minimal Markdown → HTML converter  (no dependencies)
# ---------------------------------------------------------------------------
def md_to_html(md):
    """Convert a subset of Markdown to HTML.

    Supported:
    - Headings (## … ######)
    - Bold (**text**), italic (*text* / _text_), inline code (`code`)
    - Images ![alt](src)
    - Links [text](url)
    - Unordered lists (- item)
    - Ordered lists (1. item)
    - Fenced code blocks (``` ... ```)
    - Block quotes (> text)
    - Horizontal rules (--- or ***)
    - YouTube / Vimeo embeds via bare URLs on their own line
    - Paragraphs and line breaks
    """
    lines = md.split("\n")
    out = []
    i = 0
    in_ul = False
    in_ol = False
    in_blockquote = False

    def close_lists():
        nonlocal in_ul, in_ol, in_blockquote
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_blockquote:
            out.append("</blockquote>")
            in_blockquote = False

    def inline(text):
        """Process inline markdown elements."""
        # Images (before links so ![...](...) isn't consumed as a link)
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            r'<img src="\2" alt="\1" class="blog-img">',
            text
        )
        # Links
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" style="color:goldenrod;">\1</a>',
            text
        )
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<em>\1</em>', text)
        # Inline code
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        return text

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            close_lists()
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(html_module.escape(lines[i]))
                i += 1
            lang_attr = f' class="language-{lang}"' if lang else ""
            out.append(f'<pre><code{lang_attr}>{chr(10).join(code_lines)}</code></pre>')
            i += 1
            continue

        stripped = line.strip()

        # Blank line
        if not stripped:
            close_lists()
            i += 1
            continue

        # Horizontal rule
        if re.match(r'^(---+|\*\*\*+|___+)\s*$', stripped):
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        # Headings
        heading_match = re.match(r'^(#{2,6})\s+(.+)', stripped)
        if heading_match:
            close_lists()
            level = len(heading_match.group(1))
            text = inline(heading_match.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Skip h1 (title is rendered from front-matter)
        if re.match(r'^#\s+', stripped):
            i += 1
            continue

        # Video embeds: YouTube
        yt = re.match(r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+)', stripped)
        if yt and stripped == line.strip():
            close_lists()
            vid = yt.group(1)
            out.append(
                f'<div class="blog-video"><iframe src="https://www.youtube.com/embed/{vid}" '
                f'frameborder="0" allowfullscreen></iframe></div>'
            )
            i += 1
            continue

        # Video embeds: Vimeo
        vm = re.match(r'https?://(?:www\.)?vimeo\.com/(\d+)', stripped)
        if vm and stripped == line.strip():
            close_lists()
            vid = vm.group(1)
            out.append(
                f'<div class="blog-video"><iframe src="https://player.vimeo.com/video/{vid}" '
                f'frameborder="0" allowfullscreen></iframe></div>'
            )
            i += 1
            continue

        # Block quotes
        if stripped.startswith(">"):
            if not in_blockquote:
                close_lists()
                out.append("<blockquote>")
                in_blockquote = True
            text = inline(stripped[1:].strip())
            out.append(f"<p>{text}</p>")
            i += 1
            continue

        # Unordered list
        ul_match = re.match(r'^[-*+]\s+(.+)', stripped)
        if ul_match:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if in_blockquote:
                out.append("</blockquote>")
                in_blockquote = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(ul_match.group(1))}</li>")
            i += 1
            continue

        # Ordered list
        ol_match = re.match(r'^\d+\.\s+(.+)', stripped)
        if ol_match:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if in_blockquote:
                out.append("</blockquote>")
                in_blockquote = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(ol_match.group(1))}</li>")
            i += 1
            continue

        # Paragraph — gather consecutive non-blank lines
        close_lists()
        para_lines = []
        while i < len(lines) and lines[i].strip():
            s = lines[i].strip()
            if (s.startswith("#") or s.startswith("```") or s.startswith(">")
                    or re.match(r'^[-*+]\s+', s) or re.match(r'^\d+\.\s+', s)
                    or re.match(r'^(---+|\*\*\*+|___+)\s*$', s)):
                break
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            out.append(f"<p>{inline('<br>'.join(para_lines))}</p>")
        continue

    close_lists()
    return "\n".join(out)


# ---------------------------------------------------------------------------
#  Slug generator
# ---------------------------------------------------------------------------
def slugify(title):
    """Turn a title into a filename-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


# ---------------------------------------------------------------------------
#  Build a single post
# ---------------------------------------------------------------------------
def build_post(md_path, template):
    """Convert a .md file to .html, return metadata dict or None on error."""
    with open(md_path, "r", encoding="utf-8") as f:
        raw = f.read()

    meta, body = parse_frontmatter(raw)
    content_html = md_to_html(body)
    slug = slugify(meta["title"])
    html_filename = slug + ".html"
    html_path = os.path.join(POSTS_DIR, html_filename)

    rendered = template
    rendered = rendered.replace("{{TITLE}}", html_module.escape(meta["title"]))
    rendered = rendered.replace("{{DATE}}", html_module.escape(meta["date"]))
    rendered = rendered.replace("{{META_DESCRIPTION}}", html_module.escape(meta["description"]))
    rendered = rendered.replace("{{CONTENT}}", content_html)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"  Built: {html_filename}")
    meta["slug"] = slug
    meta["html_filename"] = html_filename
    return meta


# ---------------------------------------------------------------------------
#  Update index.html
# ---------------------------------------------------------------------------
def update_index(posts_meta):
    """Rewrite the blog tree in index.html."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index_html = f.read()

    if not posts_meta:
        tree_items = '\t\t\t\t<li class="blog-tree-empty font1">No posts yet — check back soon!</li>\n'
    else:
        # Sort by date, newest first
        sorted_posts = sorted(
            posts_meta,
            key=lambda p: p.get("date", ""),
            reverse=True
        )
        tree_lines = []
        for p in sorted_posts:
            date_str = f'<span class="blog-tree-date">{html_module.escape(p["date"])}</span> ' if p["date"] else ""
            title_esc = html_module.escape(p["title"])
            tree_lines.append(
                f'\t\t\t\t<li class="blog-tree-item">'
                f'<a class="font1 blog-tree-link" href="posts/{p["html_filename"]}">'
                f'{date_str}{title_esc}</a></li>'
            )
        tree_items = "\n".join(tree_lines) + "\n"

    pattern = r'(<!-- BLOG_INDEX -->\n).*?(<!-- END_BLOG_INDEX -->)'
    index_html = re.sub(pattern, r'\1' + tree_items + r'\t\t\t\t\2', index_html, flags=re.DOTALL)

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"  Index updated with {len(posts_meta)} post(s).")


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main():
    if "--new" in sys.argv:
        os.makedirs(POSTS_DIR, exist_ok=True)
        os.startfile(POSTS_DIR)
        return

    # Ensure posts dir exists
    os.makedirs(POSTS_DIR, exist_ok=True)

    # Read template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # Find all .md files
    md_files = sorted([
        f for f in os.listdir(POSTS_DIR) if f.endswith(".md")
    ])

    if not md_files:
        print("No .md files found in posts/. Add markdown files and run again.")
        update_index([])
        return

    print(f"Found {len(md_files)} markdown file(s).\n")

    all_meta = []
    for md_file in md_files:
        md_path = os.path.join(POSTS_DIR, md_file)
        meta = build_post(md_path, template)
        if meta:
            all_meta.append(meta)

    print()
    update_index(all_meta)
    print("\nDone!")


if __name__ == "__main__":
    main()
