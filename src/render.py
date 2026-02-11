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


# =====================================================
# 🔥 위험도 점수 계산 (뉴스용 예측)
# =====================================================
def calculate_news_risk_score(title: str, reason: str) -> int:
    score = 0
    text = f"{title or ''} {reason or ''}".lower()

    if any(k in text for k in ["scrape", "crawl", "unauthorised", "unauthorized"]):
        score += 30
    if any(k in text for k in ["train", "training", "model", "llm"]):
        score += 30
    if any(k in text for k in ["copyright", "dmca", "infringement"]):
        score += 20
    if any(k in text for k in ["class action"]):
        score += 10
    if any(k in text for k in ["billion", "$"]):
        score += 10

    return min(score, 100)


def format_risk(score: int) -> str:
    if score >= 80:
        return f"🔥 {score}"
    if score >= 60:
        return f"⚠️ {score}"
    if score >= 40:
        return f"🟡 {score}"
    return f"🟢 {score}"


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
    # 📰 뉴스/RSS 기반 소송 요약 + 위험도 예측
    # =====================================================
    if lawsuits:
        lines.append("## 📰 뉴스/RSS 기반 소송 요약")
        lines.append("| 일자 | 제목 | 소송번호 | 사유 | 위험도 예측 점수 |")
        lines.append(_md_sep(5))

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

            risk_score = calculate_news_risk_score(display_title, s.reason)
            risk_display = format_risk(risk_score)

            lines.append(
                f"| {_esc(s.update_or_filed_date)} | "
                f"{title_cell} | "
                f"{_esc(s.case_number)} | "
                f"{_short(s.reason)} | "
                f"{risk_display} |"
            )

        lines.append("")

    # =====================================================
    # 📘 AI 학습 위험도 점수 평가 척도 (Fold)
    # =====================================================
    lines.append("<details>")
    lines.append(
        '<summary><span style="font-size:1.2em; font-weight:bold;">📘 AI 학습 위험도 점수(0~100) 평가 척도</span></summary>\n'
    )
    lines.append("- 0~39 🟢 : AI 학습과 간접적 연관")
    lines.append("- 40~59 🟡 : AI 학습 관련 쟁점 존재")
    lines.append("- 60~79 ⚠️ : AI 모델 학습 직접 언급 및 저작권 분쟁")
    lines.append("- 80~100 🔥 : 무단 수집 + 모델 학습 + 상업적 사용 + 대규모 손해배상 등 고위험 사건")
    lines.append("")
    lines.append("### 📊 점수 산정 기준")
    lines.append("- 무단 수집(scrape/crawl 등) +30")
    lines.append("- 모델 학습(train/model/LLM 등) +30")
    lines.append("- 저작권 침해 +20")
    lines.append("- 집단소송 +10")
    lines.append("- 고액 손해배상 언급 +10")
    lines.append("</details>\n")

    return "\n".join(lines)
