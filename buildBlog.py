"""
buildBlog.py — Converts markdown files in posts/ into styled HTML blog pages
and updates the blog index (index.html).

Usage:
    python buildBlog.py            Build all posts and rebuild index
    python buildBlog.py --new      Open posts/ folder to add a new markdown file
"""

import os
import re
import sys
import shutil
import datetime
import html as html_module

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(SCRIPT_DIR, "posts")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "blog_template.html")
INDEX_PATH = os.path.join(SCRIPT_DIR, "index.html")
BUILD_INFO_PATH = os.path.join(SCRIPT_DIR, ".last_build.txt")


# ---------------------------------------------------------------------------
#  Markdown Link Updater
# ---------------------------------------------------------------------------
def update_markdown_links(text):
    """
    Ensure all links in the markdown text adhere to proper markdown syntax:
    - Leaves existing markdown links [text](url) and images ![alt](url) untouched.
    - Leaves fenced code blocks and inline code untouched.
    - Leaves standalone video embed URLs on their own line untouched.
    - Converts <http...> autolinks to [http...](http...).
    - Converts bare http(s) URLs to [url](url), correctly stripping trailing punctuation.
    """
    lines = text.split("\n")
    out_lines = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Check for fenced code block toggle
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            out_lines.append(line)
            continue

        if in_code_block:
            out_lines.append(line)
            continue

        # Keep standalone YouTube/Vimeo embeds intact on their own line
        if re.match(r'^\s*https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|vimeo\.com/)\S+\s*$', line):
            out_lines.append(line)
            continue

        # Protect inline code `...`
        code_tokens = []
        def code_repl(m):
            code_tokens.append(m.group(0))
            return f"\x00CODE_{len(code_tokens)-1}\x00"

        processed = re.sub(r'`[^`]+`', code_repl, line)

        # Convert <https?...> autolinks to markdown [url](url)
        processed = re.sub(r'<(https?://[^>]+)>', r'[\1](\1)', processed)

        # Protect existing markdown links and images: [text](url) or ![alt](url)
        link_tokens = []
        def link_repl(m):
            link_tokens.append(m.group(0))
            return f"\x00LINK_{len(link_tokens)-1}\x00"

        processed = re.sub(r'!?\[[^\]]*\]\([^)]+\)', link_repl, processed)

        # Convert remaining bare URLs to [url](url)
        def bare_url_repl(m):
            raw_url = m.group(0)
            trailing = ""
            # Strip trailing punctuation/markdown markers that shouldn't belong to the URL
            while raw_url and raw_url[-1] in ".,!?:;*_)~>\"'":
                if raw_url[-1] == ")" and raw_url.count("(") >= raw_url.count(")"):
                    break
                trailing = raw_url[-1] + trailing
                raw_url = raw_url[:-1]

            if not raw_url:
                return trailing
            return f"[{raw_url}]({raw_url}){trailing}"

        processed = re.sub(r'https?://[^\s<>]+', bare_url_repl, processed)

        # Restore protected tokens
        for i, tok in enumerate(link_tokens):
            processed = processed.replace(f"\x00LINK_{i}\x00", tok)
        for i, tok in enumerate(code_tokens):
            processed = processed.replace(f"\x00CODE_{i}\x00", tok)

        out_lines.append(processed)

    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
#  Front-matter Parser and Automatic Fixer
# ---------------------------------------------------------------------------
def fix_and_parse_frontmatter(text, filename=""):
    """
    Parse front-matter, automatically fixing missing title and date:
    - If title is missing or 'Untitled', checks for first '# Heading' or prompts the user.
    - If date is missing, grabs today's date (YYYY-MM-DD).
    - Ensures valid YAML front-matter block at the top.
    Returns (meta_dict, body_markdown, updated_full_text).
    """
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)

    if not fm_match:
        # No front-matter block found
        title_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            try:
                title = input(f"Enter title for '{filename}': ").strip()
            except (EOFError, OSError):
                title = ""
            if not title:
                title = os.path.splitext(filename)[0].replace("-", " ").title() or "Untitled"

        meta = {
            "title": title,
            "date": today_str,
            "description": ""
        }
        body = text.strip()
        updated_full_text = f"---\ntitle: {meta['title']}\ndate: {meta['date']}\ndescription: {meta['description']}\n---\n\n{body}\n"
        return meta, body, updated_full_text

    raw_yaml = fm_match.group(1)
    body = text[fm_match.end():]
    meta = {}
    lines = raw_yaml.splitlines()

    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()

    title = meta.get("title", "").strip()
    if not title or title.lower() == "untitled":
        title_match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            try:
                title = input(f"Enter title for '{filename}': ").strip()
            except (EOFError, OSError):
                title = ""
            if not title:
                title = os.path.splitext(filename)[0].replace("-", " ").title() or "Untitled"
        meta["title"] = title

    date = meta.get("date", "").strip()
    if not date:
        date = today_str
        meta["date"] = date

    meta.setdefault("description", "")

    # Reconstruct front-matter preserving keys
    new_yaml_lines = []
    seen_keys = set()
    for line in lines:
        if ":" in line:
            k, _ = line.split(":", 1)
            k_clean = k.strip().lower()
            if k_clean in meta:
                new_yaml_lines.append(f"{k_clean}: {meta[k_clean]}")
                seen_keys.add(k_clean)
            else:
                new_yaml_lines.append(line)
        else:
            new_yaml_lines.append(line)

    for required_key in ["title", "date", "description"]:
        if required_key not in seen_keys:
            new_yaml_lines.append(f"{required_key}: {meta.get(required_key, '')}")

    updated_full_text = f"---\n{chr(10).join(new_yaml_lines)}\n---\n{body}"
    return meta, body, updated_full_text


# ---------------------------------------------------------------------------
#  Minimal Markdown → HTML converter
# ---------------------------------------------------------------------------
def md_to_html(md):
    """Convert a subset of Markdown to HTML."""
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

    def parse_table_row(line):
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        # Protect pipes inside inline code `...`
        code_spans = []
        def code_repl(m):
            code_spans.append(m.group(0))
            return f"\x00TBL_CODE_{len(code_spans)-1}\x00"

        masked = re.sub(r'`[^`]+`', code_repl, s)
        raw_cells = re.split(r'(?<!\\)\|', masked)
        cells = []
        for c in raw_cells:
            cell_str = c.strip().replace(r'\|', '|')
            for idx, span in enumerate(code_spans):
                cell_str = cell_str.replace(f"\x00TBL_CODE_{idx}\x00", span)
            cells.append(cell_str)
        return cells

    def parse_table_delimiter(line):
        s = line.strip()
        if not s or not ("|" in s or re.match(r'^:?-+:?$', s)):
            return None
        cells = parse_table_row(s)
        if not cells:
            return None
        alignments = []
        for c in cells:
            m = re.match(r'^(:?)(-+)(:?)$', c)
            if not m:
                return None
            left, _, right = m.groups()
            if left and right:
                alignments.append("center")
            elif right:
                alignments.append("right")
            elif left:
                alignments.append("left")
            else:
                alignments.append(None)
        return alignments

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

        # Headings (h2-h6)
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

        # Tables
        if "|" in stripped and i + 1 < len(lines):
            alignments = parse_table_delimiter(lines[i + 1])
            if alignments is not None:
                headers = parse_table_row(stripped)
                if headers:
                    close_lists()
                    num_cols = max(len(headers), len(alignments))
                    align_attrs = []
                    for a in alignments:
                        if a:
                            align_attrs.append(f' style="text-align: {a};"')
                        else:
                            align_attrs.append("")
                    while len(align_attrs) < num_cols:
                        align_attrs.append("")

                    table_lines = ['<table>', '<thead>', '<tr>']
                    for col_idx in range(num_cols):
                        h_text = headers[col_idx] if col_idx < len(headers) else ""
                        attr = align_attrs[col_idx]
                        table_lines.append(f'<th{attr}>{inline(h_text)}</th>')
                    table_lines.append('</tr>')
                    table_lines.append('</thead>')
                    table_lines.append('<tbody>')

                    i += 2  # Skip header and delimiter lines

                    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                        if parse_table_delimiter(lines[i]) is not None:
                            i += 1
                            continue
                        row_cells = parse_table_row(lines[i])
                        table_lines.append('<tr>')
                        for col_idx in range(num_cols):
                            c_text = row_cells[col_idx] if col_idx < len(row_cells) else ""
                            attr = align_attrs[col_idx]
                            table_lines.append(f'<td{attr}>{inline(c_text)}</td>')
                        table_lines.append('</tr>')
                        i += 1

                    table_lines.append('</tbody>')
                    table_lines.append('</table>')
                    out.append("\n".join(table_lines))
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
            if "|" in s and i + 1 < len(lines) and parse_table_delimiter(lines[i + 1]) is not None:
                break
            para_lines.append(lines[i].strip())
            i += 1
        if para_lines:
            out.append(f"<p>{inline('<br>'.join(para_lines))}</p>")
        continue

    close_lists()
    return "\n".join(out)


# ---------------------------------------------------------------------------
#  Slug Generator
# ---------------------------------------------------------------------------
def slugify(title):
    """Turn a title into a filename-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or "post"


# ---------------------------------------------------------------------------
#  Sorting posts by date
# ---------------------------------------------------------------------------
def post_sort_key(p):
    """Sort newest dates first, placing non-standard dates appropriately."""
    d = p.get("date", "")
    if re.match(r'^\d{4}-\d{2}-\d{2}', d):
        return (1, d)
    if d:
        return (0, d)
    return (-1, "")


# ---------------------------------------------------------------------------
#  Build post pages with sidebar tree
# ---------------------------------------------------------------------------
def render_post_html(meta, content_html, sorted_posts, template):
    """Render a post with its own sidebar tree where the current post is highlighted."""
    sidebar_lines = []
    for item in sorted_posts:
        date_str = f'<span class="blog-tree-date">{html_module.escape(item["date"])}</span> ' if item["date"] else ""
        title_esc = html_module.escape(item["title"])
        if item.get("slug") == meta.get("slug"):
            # Current post highlighted
            sidebar_lines.append(
                f'\t\t\t\t<li class="blog-tree-item blog-tree-item-current">'
                f'<span class="font1 blog-tree-current">{date_str}{title_esc}</span></li>'
            )
        else:
            # Other posts clickable
            sidebar_lines.append(
                f'\t\t\t\t<li class="blog-tree-item">'
                f'<a class="font1 blog-tree-link" href="{item["html_filename"]}">'
                f'{date_str}{title_esc}</a></li>'
            )

    sidebar_posts_html = "\n".join(sidebar_lines)

    rendered = template
    rendered = rendered.replace("{{TITLE}}", html_module.escape(meta["title"]))
    rendered = rendered.replace("{{DATE}}", html_module.escape(meta["date"]))
    rendered = rendered.replace("{{META_DESCRIPTION}}", html_module.escape(meta.get("description", "")))
    rendered = rendered.replace("{{CONTENT}}", content_html)
    rendered = rendered.replace("{{SIDEBAR_POSTS}}", sidebar_posts_html)
    return rendered


# ---------------------------------------------------------------------------
#  Update index.html
# ---------------------------------------------------------------------------
def update_index(sorted_posts):
    """Rewrite the blog tree in index.html."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index_html = f.read()

    if not sorted_posts:
        tree_items = '\t\t\t\t<li class="blog-tree-empty font1">No posts yet — check back soon!</li>\n'
    else:
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

    print(f"  Index updated with {len(sorted_posts)} post(s).")


# ---------------------------------------------------------------------------
#  Main build routine
# ---------------------------------------------------------------------------
def main():
    if "--new" in sys.argv:
        os.makedirs(POSTS_DIR, exist_ok=True)
        os.startfile(POSTS_DIR)
        return

    os.makedirs(POSTS_DIR, exist_ok=True)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    md_files = sorted([f for f in os.listdir(POSTS_DIR) if f.endswith(".md")])
    if not md_files:
        print("No .md files found in posts/. Add markdown files and run again.")
        update_index([])
        return

    print(f"Found {len(md_files)} markdown file(s).\n")

    posts_data = []
    new_html_files = []

    # Step 1: Read, update links, fix title/date, prepare content
    for md_file in md_files:
        md_path = os.path.join(POSTS_DIR, md_file)
        with open(md_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Update links inside markdown to correct syntax
        text_with_fixed_links = update_markdown_links(raw_text)

        # Fix title and date section
        meta, body, updated_text = fix_and_parse_frontmatter(text_with_fixed_links, filename=md_file)

        # Write back if file was updated
        if updated_text != raw_text:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(updated_text)
            print(f"  Updated markdown: {md_file} (fixed syntax/meta)")

        slug = slugify(meta["title"])
        html_filename = slug + ".html"
        html_path = os.path.join(POSTS_DIR, html_filename)

        # Track if this HTML post is newly created
        if not os.path.exists(html_path):
            new_html_files.append(html_path)

        meta["slug"] = slug
        meta["html_filename"] = html_filename
        meta["html_path"] = html_path
        meta["body"] = body

        posts_data.append(meta)

    # Sort posts newest first
    sorted_posts = sorted(posts_data, key=post_sort_key, reverse=True)

    # Step 2: Build HTML for each post
    for p in sorted_posts:
        content_html = md_to_html(p["body"])
        rendered = render_post_html(p, content_html, sorted_posts, template)

        with open(p["html_path"], "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"  Built: {p['html_filename']}")

    # Step 3: Update index.html
    print()
    update_index(sorted_posts)

    # Step 4: Write build metadata for batch deployment script
    # Line 1: Blog post title (for git commit message)
    # Line 2+: Newly created html files
    latest_title = sorted_posts[0]["title"] if sorted_posts else "Update blog"
    with open(BUILD_INFO_PATH, "w", encoding="utf-8") as f:
        f.write(latest_title + "\n")
        for nf in new_html_files:
            rel_nf = os.path.relpath(nf, SCRIPT_DIR).replace("\\", "/")
            f.write(rel_nf + "\n")

    print("\nDone!")


if __name__ == "__main__":
    main()
