from __future__ import annotations
import re
from typing import List, Set, Tuple
from .utils import debug_log

def extract_section(md_text: str, section_title: str) -> str:
    """Markdown 텍스트에서 특정 섹션 제목 아래의 내용을 추출합니다."""
    lines = md_text.split("\n")
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip().startswith(section_title):
            start = i + 1
            continue
        if start and line.startswith("## "):
            end = i
            break
    if start is None:
        return ""
    if end is None:
        end = len(lines)
    return "\n".join(lines[start:end])

def parse_table(section_md: str) -> Tuple[List[str], List[List[str]], Tuple[str, str]]:
    """Markdown 테이블을 헤더, 행 데이터, 메타데이터(헤더/구분선 라인)로 파싱합니다."""
    lines = [l for l in section_md.split("\n") if l.strip().startswith("|")]
    if len(lines) < 3:
        return [], [], ("", "")

    header = lines[0]
    separator = lines[1]
    rows = lines[2:]

    def split_row(row_text: str) -> List[str]:
        # 역슬래시로 이스케이프되지 않은 파이프만 분할
        return [c.strip() for c in re.split(r'(?<!\\)\|', row_text.strip())[1:-1]]

    header_cols = split_row(header)
    parsed_rows = []
    for row in rows:
        cols = split_row(row)
        if len(cols) == len(header_cols):
            parsed_rows.append(cols)
        else:
            debug_log(f"Table row column mismatch: expected {len(header_cols)}, got {len(cols)}. Row: {row[:100]}...")

    return header_cols, parsed_rows, (header, separator)

def extract_article_url(cell: str) -> str | None:
    """Markdown 링크 셀에서 URL을 추출합니다."""
    m = re.search(r"\((https?://[^\)]+)\)", cell)
    if m:
        return m.group(1).split("&hl=")[0]
    return None

def apply_deduplication(md: str, comments: List[dict]) -> str:
    """
    이전 GitHub 댓글들을 분석하여 중복된 데이터를 'skip' 처리하고 요약을 추가합니다.
    """
    if not comments:
        return md

    # 1) Base Snapshot Key Set 생성 (모든 이전 댓글 대상)
    base_article_set: Set[str] = set()
    base_docket_set: Set[str] = set()

    for comment in comments:
        body = comment.get("body") or ""
        
        # News 처리 (이전 이름 '## 📰 News'와 새 이름 '## 📰 AI Suit News' 모두 지원)
        news_section_base = extract_section(body, "## 📰 AI Suit News") or extract_section(body, "## 📰 News")
        h_news, r_news, _ = parse_table(news_section_base)
        if "제목" in h_news:
            idx = h_news.index("제목")
            for r in r_news:
                url = extract_article_url(r[idx])
                if url:
                    base_article_set.add(url)
        
        # Cases 처리
        recap_section_base = extract_section(body, "## ⚖️ Cases")
        h_cases, r_cases, _ = parse_table(recap_section_base)
        if "도켓번호" in h_cases:
            idx = h_cases.index("도켓번호")
            for r in r_cases:
                base_docket_set.add(r[idx])

    # 2) 현재 Markdown 처리 (News - 새 이름 사용)
    current_md = md
    news_section = extract_section(current_md, "## 📰 AI Suit News")
    n_headers, n_rows, n_table_meta = parse_table(news_section)

    new_article_count = 0
    total_article_count = len(n_rows)

    if n_headers and "제목" in n_headers:
        title_idx = n_headers.index("제목")
        no_idx = n_headers.index("No.") if "No." in n_headers else None
        date_idx = n_headers.index("기사일자⬇️") if "기사일자⬇️" in n_headers else None

        header_line, separator_line = n_table_meta
        non_skip_rows = []

        for r in n_rows:
            url = extract_article_url(r[title_idx])
            if url in base_article_set:
                debug_log(f"Skipping duplicate News: {r[title_idx]} ({url})")
            else:
                non_skip_rows.append(r)
                new_article_count += 1
        
        if new_article_count == 0:
            new_news_section = "새로운 소식이 0건입니다.\n"
        else:
            final_rows = non_skip_rows
            new_lines = [header_line, separator_line]
            for row_idx, r in enumerate(final_rows, start=1):
                if no_idx is not None:
                    r[no_idx] = str(row_idx)
                new_lines.append("| " + " | ".join(r) + " |")
            new_news_section = "\n".join(new_lines)
        current_md = current_md.replace(news_section, new_news_section)

    # 3) 현재 Markdown 처리 (Cases)
    recap_section = extract_section(current_md, "## ⚖️ Cases")
    c_headers, c_rows, c_table_meta = parse_table(recap_section)

    new_docket_count = 0
    total_docket_count = len(c_rows)

    if c_headers and "도켓번호" in c_headers:
        docket_idx = c_headers.index("도켓번호")
        no_idx = c_headers.index("No.") if "No." in c_headers else None
        status_idx = c_headers.index("상태") if "상태" in c_headers else None
        case_idx = c_headers.index("케이스명") if "케이스명" in c_headers else None

        header_line, separator_line = c_table_meta
        non_skip_rows = []

        for r in c_rows:
            docket = r[docket_idx]
            if docket in base_docket_set:
                debug_log(f"Skipping duplicate Case: {r[case_idx]} ({docket})")
            else:
                non_skip_rows.append(r)
                new_docket_count += 1

        if new_docket_count == 0:
            new_recap_section = "새로운 소식이 0건입니다.\n"
        else:
            final_rows = non_skip_rows
            new_lines = [header_line, separator_line]
            for row_idx, r in enumerate(final_rows, start=1):
                if no_idx is not None:
                    r[no_idx] = str(row_idx)
                new_lines.append("| " + " | ".join(r) + " |")
            new_recap_section = "\n".join(new_lines)
        current_md = current_md.replace(recap_section, new_recap_section)

    # 4) 중복 제거 요약 생성
    base_news = len(base_article_set)
    base_cases = len(base_docket_set)
    dup_news = total_article_count - new_article_count
    dup_cases = total_docket_count - new_docket_count

    new_news_label = f"**{new_article_count} (New)**" + (" 🔴" if new_article_count > 0 else "")
    new_cases_label = f"**{new_docket_count} (New)**" + (" 🔴" if new_docket_count > 0 else "")

    summary_header = (
        "### 중복 제거 요약:\n"
        "🔁 Dedup Summary\n"
        f"└ News {base_news} (Baseline): "
        f"{dup_news} (Dup), "
        f"{new_news_label}\n"
        f"└ Cases {base_cases} (Baseline): "
        f"{dup_cases} (Dup), "
        f"{new_cases_label}\n\n"
    )

    return summary_header + current_md
