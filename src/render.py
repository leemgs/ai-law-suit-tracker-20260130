from __future__ import annotations
from typing import List
from .extract import Lawsuit
from .courtlistener import CLDocument, CLCaseSummary


def _esc(s: str) -> str:
    s = str(s or "").strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("```", "&#96;&#96;&#96;")
    s = s.replace("~~~", "&#126;&#126;&#126;")
    s = s.replace("|", "\\|")
    s = s.replace("\n", "<br>")
    return s


def _md_sep(col_count: int) -> str:
    return "|" + "---| " * col_count


def _mdlink(label: str, url: str) -> str:
    label = _esc(label)
    url = (url or "").strip()
    if not url:
        return label
    return f"[{label}]({url})"


def _details(summary: str, body: str) -> str:
    body = body or ""
    if not body or body == "미확인":
        return "미확인"
    return f"<details><summary>{_esc(summary)}</summary>{_esc(body)}</details>"


def _short(val: str, limit: int = 140) -> str:
    val = val or ""
    if len(val) <= limit:
        return _esc(val)
    return _details("내용 펼치기", val)


def render_markdown(
    lawsuits: List[Lawsuit],
    cl_docs: List[CLDocument],
    cl_cases: List[CLCaseSummary],
    lookback_days: int = 3,
) -> str:

    lines: List[str] = []

    os = __import__("os")
    show_candidates = os.getenv("SHOW_DOCKET_CANDIDATES", "").lower() in ("1", "true", "yes", "y")
    collapse_article_urls = os.getenv("COLLAPSE_ARTICLE_URLS", "").lower() in ("1", "true", "yes", "y")

    # =====================================================
    # 📊 KPI 카드형 요약
    # =====================================================
    lines.append(f"## 📊 최근 {lookback_days}일 요약\n")
    lines.append("| 구분 | 건수 |")
    lines.append("|---|---|")
    lines.append(f"| 📰 뉴스 수집 | **{len(lawsuits)}** |")
    lines.append(f"| ⚖️ RECAP 사건 | **{len(cl_cases)}** |")
    lines.append(f"| 📄 RECAP 문서 | **{len(cl_docs)}** |\n")

    # Quick Navigation
    lines.append("## 🔎 빠른 이동")
    lines.append("- [🔥 820 Copyright](#-820-copyright)")
    lines.append("- [📁 Others](#-others)")
    lines.append("- [📄 RECAP 문서](#-recap-문서-기반-complaintpetition-우선)")
    lines.append("- [📰 기사 주소](#기사-주소)\n")

    # =====================================================
    # 📰 뉴스 테이블
    # =====================================================
    if lawsuits:
        lines.append("## 📰 뉴스/RSS 기반 소송 요약")
        lines.append("| 일자 | 제목 | 소송번호 | 사유 | 원고 | 피고 | 국가 | 법원 |")
        lines.append(_md_sep(8))

        for s in lawsuits:

            if (s.case_title and s.case_title != "미확인") and (
                s.article_title and s.article_title != s.case_title
            ):
                display_title = f"{s.case_title} / {s.article_title}"
            elif s.case_title and s.case_title != "미확인":
                display_title = s.case_title
            else:
                display_title = s.article_title or s.case_title

            article_url = s.article_urls[0] if getattr(s, "article_urls", None) else ""
            title_cell = _mdlink(display_title, article_url)

            lines.append(
                f"| {_esc(s.update_or_filed_date)} | {title_cell} | {_esc(s.case_number)} | {_short(s.reason)} | {_esc(s.plaintiff)} | {_esc(s.defendant)} | {_esc(s.country)} | {_esc(s.court)} |"
            )

        lines.append("\n---\n")

    # =====================================================
    # ⚖️ RECAP 케이스 분리
    # =====================================================
    if cl_cases:

        copyright_cases = []
        other_cases = []

        for c in cl_cases:
            nature = (c.nature_of_suit or "").lower()
            if "820" in nature and "copyright" in nature:
                copyright_cases.append(c)
            else:
                other_cases.append(c)

        def render_recap_table(cases: List[CLCaseSummary]):
            lines.append("| 상태 | 접수일 | 케이스명 | 도켓번호 | 법원 | Nature | Cause | Complaint |")
            lines.append(_md_sep(8))

            for c in sorted(cases, key=lambda x: x.date_filed, reverse=True)[:25]:

                lines.append(
                    f"| {_esc(c.status)} | "
                    f"{_esc(c.date_filed)} | "
                    f"{_mdlink(c.case_name, f'https://www.courtlistener.com/docket/{c.docket_id}/')} | "
                    f"{_esc(c.docket_number)} | "
                    f"{_esc(c.court)} | "
                    f"{_esc(c.nature_of_suit)} | "
                    f"{_short(c.cause)} | "
                    f"{_mdlink('Complaint', c.complaint_link)} |"
                )

        # 🔥 820 강조
        lines.append("## 🔥 820 Copyright")
        if copyright_cases:
            render_recap_table(copyright_cases)
        else:
            lines.append("820 Copyright 사건 없음\n")

        # 📁 Others 접기
        lines.append("\n<details>")
        lines.append("<summary>## 📁 Others</summary>\n")

        if other_cases:
            render_recap_table(other_cases)
        else:
            lines.append("Others 사건 없음\n")

        lines.append("</details>\n")

    # =====================================================
    # 📄 RECAP 문서
    # =====================================================
    if cl_docs:
        lines.append("## 📄 RECAP 문서 기반 (Complaint/Petition 우선)")
        lines.append("| 제출일 | 케이스 | 문서유형 | 원고 | 피고 | 핵심 | 문서 |")
        lines.append(_md_sep(7))

        for d in sorted(cl_docs, key=lambda x: x.date_filed, reverse=True)[:20]:
            link = d.document_url or d.pdf_url
            lines.append(
                f"| {_esc(d.date_filed)} | {_esc(d.case_name)} | {_esc(d.doc_type)} | "
                f"{_esc(d.extracted_plaintiff)} | {_esc(d.extracted_defendant)} | "
                f"{_short(d.extracted_ai_snippet)} | {_mdlink('Document', link)} |"
            )

        lines.append("")

    # =====================================================
    # 📰 기사 주소
    # =====================================================
    lines.append("## 기사 주소\n")

    if lawsuits:
        for s in lawsuits:

            if (s.case_title and s.case_title != "미확인") and (
                s.article_title and s.article_title != s.case_title
            ):
                header_title = f"{s.case_title} / {s.article_title}"
            elif s.case_title and s.case_title != "미확인":
                header_title = s.case_title
            else:
                header_title = s.article_title or s.case_title

            lines.append(f"### {_esc(header_title)} ({_esc(s.case_number)})")

            if collapse_article_urls and s.article_urls:
                lines.append("<details><summary>기사 주소 펼치기</summary>")
                for u in s.article_urls:
                    lines.append(f"- {u}")
                lines.append("</details>")
            else:
                for u in s.article_urls:
                    lines.append(f"- {u}")

            lines.append("")

    return "\n".join(lines)
