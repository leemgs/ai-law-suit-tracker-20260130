from __future__ import annotations
from typing import List
from .extract import Lawsuit
from .courtlistener import CLDocument, CLCaseSummary

def _esc(s: str) -> str:
    return (s or "").replace("|", "\|").replace("\n", " ").strip()

def render_markdown(lawsuits: List[Lawsuit], cl_docs: List[CLDocument], cl_cases: List[CLCaseSummary]) -> str:
    lines: List[str] = []
    lines.append("## 최근 3일: AI 학습용 무단/불법 데이터 사용 관련 소송/업데이트\n")

    if lawsuits:
        lines.append("### 요약 테이블 (뉴스/RSS 기반 정규화)")
        lines.append("| 소송/업데이트 일자 | 소송제목 | 소송번호 | 소송이유 | 원고 | 피고 | 국가 | 법원명 | 히스토리 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for s in lawsuits:
            lines.append(
                f"| {_esc(s.update_or_filed_date)} | {_esc(s.case_title)} | {_esc(s.case_number)} | {_esc(s.reason)} | {_esc(s.plaintiff)} | {_esc(s.defendant)} | {_esc(s.country)} | {_esc(s.court)} | {_esc(s.history)} |"
            )
    else:
        lines.append("정규화된 소송 테이블을 생성하지 못했습니다(뉴스/문서에서 필요한 필드가 부족할 수 있음).")

    lines.append("\n---\n")

    if cl_cases:
        lines.append("### RECAP 도켓 기반 케이스 요약 (소송번호 확장 필드)")
        lines.append("| 접수일 | 상태 | 케이스명 | 도켓번호 | 법원 | 담당판사 | 치안판사 | Nature of Suit | Cause | Parties | Complaint 문서# | Complaint 링크 | 최근 도켓 업데이트(3) | 청구원인(Complaint 추출) | AI학습 핵심문장(Complaint 추출) |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for c in sorted(cl_cases, key=lambda x: x.date_filed, reverse=True)[:25]:
            lines.append(
                "| {date_filed} | {status} | {case_name} | {docket_number} | {court} | {judge} | {mag} | {nos} | {cause} | {parties} | {docno} | {link} | {updates} | {ec} | {ai} |".format(
                    date_filed=_esc(c.date_filed),
                    status=_esc(c.status),
                    case_name=_esc(c.case_name),
                    docket_number=_esc(c.docket_number),
                    court=_esc(c.court),
                    judge=_esc(c.judge),
                    mag=_esc(c.magistrate),
                    nos=_esc(c.nature_of_suit),
                    cause=_esc(c.cause),
                    parties=_esc(c.parties),
                    docno=_esc(c.complaint_doc_no),
                    link=_esc(c.complaint_link),
                    updates=_esc(c.recent_updates),
                    ec=_esc(c.extracted_causes),
                    ai=_esc(c.extracted_ai_snippet),
                )
            )
        lines.append("\n")

    if cl_docs:
        lines.append("### RECAP 문서 기반 (Complaint/Petition 우선, 없으면 Motion/Order 등 핵심 문서로 보조 수집)")
        lines.append("| 문서 제출일 | 케이스명 | 도켓번호 | 법원 | 문서유형 | 원고(추출) | 피고(추출) | 청구원인(추출) | AI학습 핵심문장(추출) | 문서 링크 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for d in sorted(cl_docs, key=lambda x: x.date_filed, reverse=True)[:20]:
            link = d.document_url or d.pdf_url
            lines.append(
                f"| {_esc(d.date_filed)} | {_esc(d.case_name)} | {_esc(d.docket_number)} | {_esc(d.court)} | {_esc(d.doc_type)} | {_esc(d.extracted_plaintiff)} | {_esc(d.extracted_defendant)} | {_esc(d.extracted_causes)} | {_esc(d.extracted_ai_snippet)} | {_esc(link)} |"
            )
        lines.append("\n")

    lines.append("## 기사 주소\n")
    if lawsuits:
        for s in lawsuits:
            lines.append(f"### {_esc(s.case_title)} ({_esc(s.case_number)})")
            for u in s.article_urls:
                lines.append(f"- {u}")
            lines.append("")
    else:
        lines.append("- (기사 주소 출력 실패)")

    return "\n".join(lines)
