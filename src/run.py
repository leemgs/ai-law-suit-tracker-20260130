from __future__ import annotations
import os
from datetime import datetime, timezone

from .fetch import fetch_news
from .extract import load_known_cases, build_lawsuits_from_news
from .render import render_markdown
from .github_issue import find_or_create_issue, create_comment
from .slack import post_to_slack
from .courtlistener import search_recent_documents, build_complaint_documents_from_hits, build_case_summaries_from_hits
from .queries import COURTLISTENER_QUERIES

def main() -> None:
    # 환경 변수 로드
    owner = os.environ["GITHUB_OWNER"]
    repo = os.environ["GITHUB_REPO"]
    gh_token = os.environ["GITHUB_TOKEN"]
    slack_webhook = os.environ["SLACK_WEBHOOK_URL"]

    issue_title = os.environ.get("ISSUE_TITLE", "AI 불법/무단 학습데이터 소송 모니터링")
    issue_label = os.environ.get("ISSUE_LABEL", "ai-lawsuit-monitor")

    # 1) CourtListener 검색 + RECAP Complaint 문서 수집
    hits = []
    for q in COURTLISTENER_QUERIES:
        hits.extend(search_recent_documents(q, days=3, max_results=20))
    
    # 중복 제거 (딕셔너리 키 활용)
    dedup = {}
    for h in hits:
        key = (h.get("absolute_url") or h.get("url") or "") + "|" + (h.get("caseName") or h.get("title") or "")
        dedup[key] = h
    hits = list(dedup.values())

    cl_docs = build_complaint_documents_from_hits(hits, days=3)

    # 2) 뉴스 수집 (보강)
    news = fetch_news()
    known = load_known_cases()
    lawsuits = build_lawsuits_from_news(news, known)

    # 3) 렌더링 및 출력
    cl_cases = build_case_summaries_from_hits(hits)
    md = render_markdown(lawsuits, cl_docs, cl_cases)
    
    # 수정: 불필요한 이스케이프(\) 제거 및 중복 코드 삭제
    print("===== REPORT BEGIN =====")
    print(md[:8000])
    print("===== REPORT END =====")

    # 4) GitHub Issue 댓글 업로드
    issue_no = find_or_create_issue(owner, repo, gh_token, issue_title, issue_label)
    print(f"Issue #{issue_no} 준비 완료") # 수정: f-string 내 불필요한 \ 제거
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    comment_body = f"### 실행 결과 ({timestamp})\n\n{md}"
    create_comment(owner, repo, gh_token, issue_no, comment_body)
    print("GitHub Issue 댓글 업로드 완료")

    # 5) Slack 요약 전송
    summary_lines = [
        f"*AI 소송 모니터링 업데이트* ({timestamp})",
        f"- 정규화 테이블(뉴스 보강): {len(lawsuits)}건",
        f"- RECAP 문서(Complaint 우선): {len(cl_docs)}건",
        f"- GitHub Issue: #{issue_no}",
    ]
    
    if cl_docs:
        # date_filed 기준으로 정렬하여 상위 3개 추출
        top = sorted(cl_docs, key=lambda x: x.date_filed, reverse=True)[:3]
        summary_lines.append("- 최신 RECAP 문서:")
        for d in top:
            summary_lines.append(f"  • {d.date_filed} | {d.doc_type} | {d.case_name}")
            
    post_to_slack(slack_webhook, "\n".join(summary_lines))
    print("Slack 전송 완료")

if __name__ == "__main__":
    main()
