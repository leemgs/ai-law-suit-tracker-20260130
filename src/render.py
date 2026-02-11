from __future__ import annotations
from typing import List
from collections import Counter
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


def _short(val: str, limit: int = 140) -> str:
    val = val or ""
    if len(val) <= limit:
        return _esc(val)
    return f"<details><summary>내용 펼치기</summary>{_esc(val)}</details>"


def _generate_executive_summary(cl_cases: List[CLCaseSummary]) -> str:
    if not cl_cases:
        return "최근 범위 내 분석 가능한 사건이 없습니다."

    total_cases = len(cl_cases)
    copyright_cases = sum(
        1 for c in cl_cases
        if c.nature_of_suit and "820" in c.nature_of_suit
    )

    courts = Counter([c.court or "미확인" for c in cl_cases])
    major_court = courts.most_common(1)[0][0] if courts else "미확인"

    summary_lines = [
        f"최근 {total_cases}건의 AI 관련 소송이 확인되었습니다.",
        f"그 중 {copyright_cases}건은 820 Copyright 유형입니다.",
        "주요 쟁점은 AI 학습을 위한 무단 데이터 수집 및 저작권 침해 주장입니다.",
        f"가장 활발한 관할 법원은 {major_court} 입니다.",
        "AI 학습 데이터의 법적 책임 범위에 대한 판례 형성이 진행 중입니다."
    ]

    return "\n".join(summary_lines)


def render_markdown(
    lawsuits: List[Lawsuit],
    cl_docs: List[CLDocument],
    cl_cases: List[CLCaseSummary],
    lookback_days: int = 3,
) -> str:

    lines: List[str] = []

    # =====================================================
    # 📊 KPI 요약
    # =====================================================
    lines.append(f"## 📊 최근 {lookback_days}일 요약\n")
    lines.append("| 구분 | 건수 |")
    lines.append("|---|---|")
    lines.append(f"| 📰 뉴스 수집 | **{len(lawsuits)}** |")
    lines.append(f"| ⚖️ RECAP 사건 | **{len(cl_cases)}** |")
    lines.append(f"| 📄 RECAP 문서 | **{len(cl_docs)}** |\n")

    # =====================================================
    # 🧠 Executive Summary
    # =====================================================
    if cl_cases:
        lines.append("## 🧠 Executive Summary (AI Generated)\n")
        summary = _generate_executive_summary(cl_cases)
        for line in summary.split("\n"):
            lines.append(f"> {line}")
        lines.append("")

    # =====================================================
    # 📊 Nature 통계
    # =====================================================
    if cl_cases:
        counter = Counter([c.nature_of_suit or "미확인" for c in cl_cases])
        lines.append("## 📊 Nature of Suit 통계\n")
        lines.append("| Nature of Suit | 건수 |")
        lines.append("|---|---|")
        for k, v in counter.most_common(10):
            lines.append(f"| {_esc(k)} | **{v}** |")
        lines.append("")

    # =====================================================
    # ⚖️ RECAP 케이스 테이블
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

        def render_table(cases):

            lines.append("| 상태 | 접수일 | 케이스명 | Nature | 도켓번호 | 담당판사 | 법원명 |")
            lines.append(_md_sep(7))

            for c in sorted(cases, key=lambda x: x.date_filed, reverse=True)[:25]:

                docket_url = f"https://www.courtlistener.com/docket/{c.docket_id}/"

                lines.append(
                    f"| {_esc(c.status)} | "
                    f"{_esc(c.date_filed)} | "
                    f"{_mdlink(c.case_name, docket_url)} | "
                    f"{_esc(c.nature_of_suit)} | "
                    f"{_mdlink(c.docket_number, docket_url)} | "
                    f"{_esc(c.judge)} | "
                    f"{_esc(c.court)} |"
                )

        # 🔥 820
        lines.append("## 🔥 820 Copyright\n")
        if copyright_cases:
            render_table(copyright_cases)
        else:
            lines.append("820 사건 없음\n")

        # 📁 Others (동일 크기 + fold)
        lines.append("\n<details>")
        lines.append("<summary><strong>📁 Others</strong></summary>\n")

        if other_cases:
            render_table(other_cases)
        else:
            lines.append("Others 사건 없음\n")

        lines.append("</details>\n")

    # ===========================
