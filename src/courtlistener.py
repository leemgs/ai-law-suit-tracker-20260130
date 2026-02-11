from __future__ import annotations

import os
import re
import requests
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from .pdf_text import extract_pdf_text
from .complaint_parse import detect_causes, extract_ai_training_snippet, extract_parties_from_caption

BASE = "https://www.courtlistener.com"
SEARCH_URL = BASE + "/api/rest/v4/search/"
DOCKET_URL = BASE + "/api/rest/v4/dockets/{id}/"
DOCKETS_LIST_URL = BASE + "/api/rest/v4/dockets/"
RECAP_DOCS_URL = BASE + "/api/rest/v4/recap-documents/"
PARTIES_URL = BASE + "/api/rest/v4/parties/"
DOCKET_ENTRIES_URL = BASE + "/api/rest/v4/docket-entries/"

COMPLAINT_KEYWORDS = [
    "complaint",
    "amended complaint",
    "petition",
    "class action complaint",
]

@dataclass
class CLDocument:
    docket_id: Optional[int]
    docket_number: str
    case_name: str
    court: str
    date_filed: str
    doc_type: str
    doc_number: str
    description: str
    document_url: str
    pdf_url: str
    pdf_text_snippet: str
    extracted_plaintiff: str
    extracted_defendant: str
    extracted_causes: str
    extracted_ai_snippet: str
@dataclass
class CLCaseSummary:
    docket_id: int
    case_name: str
    docket_number: str
    court: str
    court_short_name: str
    court_api_url: str
    docket_id: int
    case_name: str
    docket_number: str
    court: str
    date_filed: str
    status: str
    judge: str
    magistrate: str
    nature_of_suit: str
    cause: str
    parties: str
    complaint_doc_no: str
    complaint_link: str
    recent_updates: str
    extracted_causes: str
    extracted_ai_snippet: str
    # (Optional) 사람이 선택할 수 있도록 매칭 후보 도켓 Top3 등을 표기
    docket_candidates: str = ""


def _headers() -> Dict[str, str]:
    token = os.getenv("COURTLISTENER_TOKEN", "").strip()
    headers = {
        "Accept": "application/json",
        "User-Agent": "ai-lawsuit-monitor/1.1",
    }
    if token:
        headers["Authorization"] = f"Token {token}"
    return headers

def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers=_headers(), timeout=25)
        if r.status_code in (401, 403):
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def _abs_url(u: str) -> str:
    if not u:
        return ""
    if u.startswith("http"):
        return u
    if u.startswith("/"):
        return BASE + u
    return u

def search_recent_documents(query: str, days: int = 3, max_results: int = 20) -> List[dict]:
    data = _get(SEARCH_URL, params={"q": query, "type": "r", "available_only": "on", "order_by": "entry_date_filed desc", "page_size": max_results})
    if not data:
        return []
    results = data.get("results", []) or []
    # 최근 3일 필터 (가능한 날짜 필드 활용)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    filtered = []
    for it in results:
        date_val = it.get("dateFiled") or it.get("date_filed") or it.get("dateCreated") or it.get("date_created")
        if date_val:
            try:
                iso = str(date_val)[:10]
                dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass
        filtered.append(it)
    return filtered

def _pick_docket_id(hit: dict) -> Optional[int]:
    # search hit 구조는 케이스/도켓/문서에 따라 달라질 수 있어 최대한 유연하게 시도
    # 1) 명시적 id 필드
    for key in ["docket_id", "docketId", "docket"]:
        v = hit.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            if v.isdigit():
                return int(v)
            m = re.search(r"/dockets/(\d+)/", v)
            if m:
                return int(m.group(1))
            m = re.search(r"/docket/(\d+)/", v)
            if m:
                return int(m.group(1))
        if isinstance(v, dict):
            if "id" in v:
                try:
                    return int(v["id"])
                except Exception:
                    pass
            for k2 in ["url", "absolute_url", "absoluteUrl"]:
                vv = v.get(k2)
                if isinstance(vv, str):
                    m = re.search(r"/dockets/(\d+)/", vv)
                    if m:
                        return int(m.group(1))
                    m = re.search(r"/docket/(\d+)/", vv)
                    if m:
                        return int(m.group(1))

    # 2) search hit의 URL(absolute_url/url)에서 추출
    for k in ["absolute_url", "absoluteUrl", "url"]:
        u = hit.get(k)
        if isinstance(u, str) and u:
            m = re.search(r"/dockets/(\d+)/", u)
            if m:
                return int(m.group(1))
            m = re.search(r"/docket/(\d+)/", u)
            if m:
                return int(m.group(1))

    return None

def _safe_str(x) -> str:
def _build_court_meta(court_raw: str) -> tuple[str, str]:
    court_raw = _safe_str(court_raw)
    if not court_raw or court_raw == "미확인":
        return "미확인", ""
    short_name = court_raw
    api_url = f"https://www.courtlistener.com/api/rest/v3/courts/{court_raw}/"
    return short_name, api_url

    return (str(x).strip() if x is not None else "")

def fetch_docket(docket_id: int) -> Optional[dict]:
    return _get(DOCKET_URL.format(id=docket_id))


def find_docket_ids_by_docket_number(docket_number: str, max_results: int = 5) -> List[int]:
    """도켓번호(예: 3:24-cv-05417)로 CourtListener 도켓 id를 찾는다.

    1) /dockets/ 리스트 엔드포인트에서 docket_number 필터 시도
    2) 실패 시 search(type=d)로 보조 검색
    """
    dn = (docket_number or "").strip()
    if not dn or dn == "미확인":
        return []

    ids: List[int] = []

    # 1) 리스트 엔드포인트
    data = _get(DOCKETS_LIST_URL, params={"docket_number": dn, "page_size": max_results})
    if data and (data.get("results") or []):
        for it in data.get("results", [])[:max_results]:
            try:
                ids.append(int(it.get("id")))
            except Exception:
                pass

    # 2) 보조: search(type=d)
    if not ids:
        s = _get(SEARCH_URL, params={"q": f'"{dn}"', "type": "d", "page_size": max_results})
        if s:
            for hit in (s.get("results") or [])[:max_results]:
                did = _pick_docket_id(hit)
                if did:
                    ids.append(int(did))

    # 중복 제거 + 0 제거
    out = []
    seen = set()
    for x in ids:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _tokenize_for_similarity(text: str) -> set[str]:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    toks = {x for x in t.split() if len(x) >= 3}
    # 너무 흔한 단어 제거
    stop = {"the", "and", "for", "with", "from", "into", "case", "lawsuit", "complaint", "petition", "amended"}
    return {x for x in toks if x not in stop}


def find_docket_candidates_by_case_title(case_title: str, max_results: int = 5) -> List[dict]:
    """케이스명(예: "Bartz et al. v. Anthropic PBC")으로 도켓 후보를 찾는다.

    반환 형식: [{"score": float, "docket_id": int, "case_name": str}, ...]
    """
    ct = (case_title or "").strip()
    if not ct or ct == "미확인":
        return []

    s = _get(SEARCH_URL, params={"q": f'"{ct}"', "type": "d", "page_size": max_results * 3})
    hits = (s.get("results") or []) if s else []

    # 약한 검색도 한 번 더(따옴표 없이)
    if not hits:
        s2 = _get(SEARCH_URL, params={"q": ct, "type": "d", "page_size": max_results * 3})
        hits = (s2.get("results") or []) if s2 else []

    want = _tokenize_for_similarity(ct)

    scored: List[tuple[float, int, str]] = []
    for h in hits:
        did = _pick_docket_id(h)
        if not did:
            continue
        cand = _safe_str(h.get("caseName") or h.get("case_name") or h.get("title") or "")
        have = _tokenize_for_similarity(cand)
        inter = len(want & have)
        union = len(want | have) or 1
        score = inter / union
        scored.append((score, int(did), cand))

    scored.sort(reverse=True)

    out: List[dict] = []
    seen = set()
    for score, did, name in scored:
        if did in seen:
            continue
        out.append({"score": float(score), "docket_id": int(did), "case_name": name})
        seen.add(did)
        if len(out) >= max_results:
            break
    return out


def find_docket_ids_by_case_title(case_title: str, max_results: int = 5) -> List[int]:
    """(호환용) 케이스명으로 도켓 id 리스트만 반환."""
    return [c["docket_id"] for c in find_docket_candidates_by_case_title(case_title, max_results=max_results)]

def list_recap_documents(docket_id: int, page_size: int = 50) -> List[dict]:
    data = _get(RECAP_DOCS_URL, params={"docket": docket_id, "page_size": page_size})
    if not data:
        return []
    return data.get("results", []) or []

def list_parties(docket_id: int, page_size: int = 200) -> List[dict]:
    data = _get(PARTIES_URL, params={"docket": docket_id, "page_size": page_size})
    if not data:
        return []
    return data.get("results", []) or []


def list_docket_entries(docket_id: int, page_size: int = 50) -> List[dict]:
    data = _get(DOCKET_ENTRIES_URL, params={"docket": docket_id, "page_size": page_size, "order_by": "-date_filed"})
    if not data:
        return []
    return data.get("results", []) or []

def _is_complaint(doc: dict) -> bool:
    hay = " ".join([_safe_str(doc.get("description")), _safe_str(doc.get("document_type"))]).lower()
    return any(k in hay for k in COMPLAINT_KEYWORDS)

def _extract_pdf_url(doc: dict) -> str:
    # CourtListener의 recap-documents 응답에서 PDF 링크 필드는 다양할 수 있어 후보를 넓게 둠
    for key in ["filepath_local", "filepathLocal", "download_url", "downloadUrl", "file", "pdf_url", "pdfUrl"]:
        v = doc.get(key)
        if isinstance(v, str) and v:
            return _abs_url(v)
    # 어떤 경우 document_url 자체가 PDF일 수 있음
    u = doc.get("absolute_url") or doc.get("url") or ""
    u = _abs_url(u)
    return u

def build_complaint_documents_from_hits(hits: List[dict], days: int = 3) -> List[CLDocument]:
    docs_out: List[CLDocument] = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    for hit in hits:
        docket_id = _pick_docket_id(hit)
        if not docket_id:
            continue

        docket = fetch_docket(docket_id) or {}
        case_name = _safe_str(docket.get("case_name") or docket.get("caseName") or hit.get("caseName") or hit.get("title"))
        docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber") or "")
        court = _safe_str(docket.get("court") or docket.get("court_id") or docket.get("courtId") or "")

        recap_docs = list_recap_documents(docket_id)
        if not recap_docs:
            continue

        # complaint 우선 + 없으면 최근 문서 1~2개라도 힌트로 남기기
        complaint_docs, mode = pick_recap_documents_with_fallback(recap_docs)
        if not complaint_docs:
            complaint_docs = sorted(recap_docs, key=lambda x: _safe_str(x.get("date_filed") or x.get("dateFiled")), reverse=True)[:2]

        for d in complaint_docs[:3]:
            doc_type = _safe_str(d.get("document_type") or d.get("documentType") or "")
            doc_number = _safe_str(d.get("document_number") or d.get("documentNumber") or d.get("document_num") or "")
            desc = _safe_str(d.get("description") or "")
            date_filed = _safe_str(d.get("date_filed") or d.get("dateFiled") or "")[:10] or datetime.now(timezone.utc).date().isoformat()

            # lookback(days) 필터
            try:
                dtf = datetime.fromisoformat(date_filed).replace(tzinfo=timezone.utc)
                if dtf < cutoff:
                    continue
            except Exception:
                pass

            document_url = _abs_url(d.get("absolute_url") or d.get("absoluteUrl") or d.get("url") or "")
            pdf_url = _extract_pdf_url(d)

            snippet = ""
            # PDF가 실제 PDF URL처럼 보일 때만 텍스트 추출 시도
            if pdf_url and (pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower()):
                snippet = extract_pdf_text(pdf_url, max_chars=3500)

            # Complaint 텍스트 기반 정밀 추출(원고/피고/청구원인/AI학습 관련 핵심문장)
            p_ex, d_ex = extract_parties_from_caption(snippet) if snippet else ("미확인", "미확인")
            causes = detect_causes(snippet) if snippet else []
            ai_snip = extract_ai_training_snippet(snippet) if snippet else ""

            docs_out.append(CLDocument(
                docket_id=docket_id,
                docket_number=docket_number or "미확인",
                case_name=case_name or "미확인",
                court=court or "미확인",
                date_filed=date_filed,
                doc_type=doc_type or ("Complaint" if _is_complaint(d) else "Document"),
                doc_number=doc_number or "미확인",
                description=desc or "미확인",
                document_url=document_url or pdf_url or "",
                pdf_url=pdf_url or "",
                pdf_text_snippet=snippet,
                extracted_plaintiff=p_ex,
                extracted_defendant=d_ex,
                extracted_causes=", ".join(causes) if causes else "미확인",
                extracted_ai_snippet=ai_snip or "",
            ))
    # 중복 제거
    uniq = {}
    for x in docs_out:
        key = (x.docket_id, x.doc_number, x.date_filed, x.document_url)
        uniq[key] = x
    return list(uniq.values())

def _format_parties(parties: List[dict], max_n: int = 12) -> str:
    names = []
    for p in parties[:max_n]:
        nm = _safe_str(p.get("name") or p.get("party_name") or p.get("partyName"))
        typ = _safe_str(p.get("party_type") or p.get("partyType") or p.get("role"))
        if nm:
            names.append(f"{nm}({typ})" if typ else nm)
    if not names:
        return "미확인"
    if len(parties) > max_n:
        names.append("…")
    return "; ".join(names)

def _status_from_docket(docket: dict) -> str:
    term = _safe_str(docket.get("date_terminated") or docket.get("dateTerminated") or "")
    if term:
        return f"종결({term[:10]})"
    return "진행중/미확인"


def build_case_summary_from_docket_id(docket_id: int) -> Optional[CLCaseSummary]:
    """도켓 id 하나로 케이스 요약을 만든다."""
    if not docket_id:
        return None

    docket = fetch_docket(int(docket_id)) or {}
    case_name = _safe_str(docket.get("case_name") or docket.get("caseName") or "") or "미확인"
    docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber") or "") or "미확인"
    court = _safe_str(docket.get("court") or docket.get("court_id") or docket.get("courtId") or "") or "미확인"

    date_filed = _safe_str(docket.get("date_filed") or docket.get("dateFiled") or "")[:10] or "미확인"
    status = _status_from_docket(docket)

    judge = _safe_str(
        docket.get("assigned_to_str")
        or docket.get("assignedToStr")
        or docket.get("assigned_to")
        or docket.get("assignedTo")
        or ""
    ) or "미확인"
    magistrate = _safe_str(
        docket.get("referred_to_str")
        or docket.get("referredToStr")
        or docket.get("referred_to")
        or docket.get("referredTo")
        or ""
    ) or "미확인"

    nature_of_suit = _safe_str(docket.get("nature_of_suit") or docket.get("natureOfSuit") or "") or "미확인"
    cause = _safe_str(docket.get("cause") or "") or "미확인"

    parties = _format_parties(list_parties(int(docket_id)))

    recap_docs = list_recap_documents(int(docket_id))
    complaint_docs = [d for d in recap_docs if _is_complaint(d)]
    complaint_doc_no = "미확인"
    complaint_link = ""
    extracted_causes = "미확인"
    extracted_ai = ""

    if complaint_docs:
        d = sorted(complaint_docs, key=lambda x: _safe_str(x.get("date_filed") or x.get("dateFiled")), reverse=True)[0]
        complaint_doc_no = _safe_str(d.get("document_number") or d.get("documentNumber") or d.get("document_num") or "") or "미확인"
        complaint_link = _abs_url(d.get("absolute_url") or d.get("absoluteUrl") or d.get("url") or "") or _extract_pdf_url(d)

        pdf_url = _extract_pdf_url(d)
        snippet = ""
        if pdf_url and (pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower()):
            snippet = extract_pdf_text(pdf_url, max_chars=4500)
        if snippet:
            causes_list = detect_causes(snippet) or []
            extracted_causes = ", ".join(causes_list) if causes_list else "미확인"
            extracted_ai = extract_ai_training_snippet(snippet) or ""

    entries = list_docket_entries(int(docket_id), page_size=20)
    updates = []
    for e in entries[:3]:
        dt = _safe_str(e.get("date_filed") or e.get("dateFiled") or "")[:10]
        desc = _safe_str(e.get("description") or e.get("text") or e.get("title") or "")
        if dt or desc:
            updates.append(f"{dt} {desc}".strip())
    recent_updates = " / ".join(updates) if updates else "미확인"

    return CLCaseSummary(
        docket_id=int(docket_id),
        case_name=case_name,
        docket_number=docket_number,
        court=court,
        date_filed=date_filed,
        status=status,
        judge=judge,
        magistrate=magistrate,
        nature_of_suit=nature_of_suit,
        cause=cause,
        parties=parties,
        complaint_doc_no=complaint_doc_no,
        complaint_link=complaint_link,
        recent_updates=recent_updates,
        extracted_causes=extracted_causes,
        extracted_ai_snippet=extracted_ai,
    )

def build_case_summaries_from_hits(hits: List[dict]) -> List[CLCaseSummary]:
    """Search hit -> docket -> parties + recap docs + docket entries로 케이스 요약을 구성."""
    summaries: List[CLCaseSummary] = []
    for hit in hits:
        docket_id = _pick_docket_id(hit)
        if not docket_id:
            continue

        docket = fetch_docket(int(docket_id)) or {}
        case_name = _safe_str(docket.get("case_name") or docket.get("caseName") or hit.get("caseName") or hit.get("title")) or "미확인"
        docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber") or "") or "미확인"
        court = _safe_str(docket.get("court") or docket.get("court_id") or docket.get("courtId") or "") or "미확인"

        date_filed = _safe_str(docket.get("date_filed") or docket.get("dateFiled") or "")[:10] or "미확인"
        status = _status_from_docket(docket)

        judge = _safe_str(docket.get("assigned_to_str") or docket.get("assignedToStr") or docket.get("assigned_to") or docket.get("assignedTo") or "")
        magistrate = _safe_str(docket.get("referred_to_str") or docket.get("referredToStr") or docket.get("referred_to") or docket.get("referredTo") or "")
        judge = judge or "미확인"
        magistrate = magistrate or "미확인"

        nature_of_suit = _safe_str(docket.get("nature_of_suit") or docket.get("natureOfSuit") or "") or "미확인"
        cause = _safe_str(docket.get("cause") or "") or "미확인"

        parties = _format_parties(list_parties(int(docket_id)))

        recap_docs = list_recap_documents(int(docket_id))
        complaint_docs = [d for d in recap_docs if _is_complaint(d)]
        complaint_doc_no = "미확인"
        complaint_link = ""
        extracted_causes = "미확인"
        extracted_ai = ""

        if complaint_docs:
            d = sorted(complaint_docs, key=lambda x: _safe_str(x.get("date_filed") or x.get("dateFiled")), reverse=True)[0]
            complaint_doc_no = _safe_str(d.get("document_number") or d.get("documentNumber") or d.get("document_num") or "") or "미확인"
            complaint_link = _abs_url(d.get("absolute_url") or d.get("absoluteUrl") or d.get("url") or "") or _extract_pdf_url(d)

            pdf_url = _extract_pdf_url(d)
            snippet = ""
            if pdf_url and (pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower()):
                snippet = extract_pdf_text(pdf_url, max_chars=4500)
            if snippet:
                causes_list = detect_causes(snippet) or []
                extracted_causes = ", ".join(causes_list) if causes_list else "미확인"
                extracted_ai = extract_ai_training_snippet(snippet) or ""

        entries = list_docket_entries(int(docket_id), page_size=20)
        updates = []
        for e in entries[:3]:
            dt = _safe_str(e.get("date_filed") or e.get("dateFiled") or "")[:10]
            desc = _safe_str(e.get("description") or e.get("text") or e.get("title") or "")
            if dt or desc:
                updates.append(f"{dt} {desc}".strip())
        recent_updates = " / ".join(updates) if updates else "미확인"

        summaries.append(CLCaseSummary(
            docket_id=int(docket_id),
            case_name=case_name,
            docket_number=docket_number,
            court=court,
            date_filed=date_filed,
            status=status,
            judge=judge,
            magistrate=magistrate,
            nature_of_suit=nature_of_suit,
            cause=cause,
            parties=parties,
            complaint_doc_no=complaint_doc_no,
            complaint_link=complaint_link,
            recent_updates=recent_updates,
            extracted_causes=extracted_causes,
            extracted_ai_snippet=extracted_ai,
        ))

    uniq = {s.docket_id: s for s in summaries}
    return list(uniq.values())


def build_case_summaries_from_docket_numbers(docket_numbers: List[str]) -> List[CLCaseSummary]:
    """뉴스/RSS 정규화 테이블의 '소송번호' 기반으로 도켓 요약을 확장."""
    out: List[CLCaseSummary] = []
    seen: set[int] = set()
    for dn in docket_numbers:
        for did in find_docket_ids_by_docket_number(dn):
            if did in seen:
                continue
            s = build_case_summary_from_docket_id(did)
            if s:
                out.append(s)
                seen.add(did)
    return out


def build_case_summaries_from_case_titles(case_titles: List[str]) -> List[CLCaseSummary]:
    """뉴스/RSS 정규화 테이블의 '소송제목'(추정 케이스명) 기반으로 도켓 요약을 확장.

    케이스명이 완벽하지 않을 수 있으므로 search(type=d) 결과를 유사도 기반으로 재정렬해 상위 후보만 사용한다.
    """
    show_candidates = os.getenv("SHOW_DOCKET_CANDIDATES", "").strip().lower() in ("1", "true", "yes", "y")

    out: List[CLCaseSummary] = []
    seen: set[int] = set()
    for ct in case_titles:
        cands = find_docket_candidates_by_case_title(ct, max_results=5)
        if not cands:
            continue

        # 자동 매칭은 1개(최상위)만 사용해 오탐을 최소화
        best = cands[0]
        did = int(best.get("docket_id") or 0)
        if not did or did in seen:
            continue

        s = build_case_summary_from_docket_id(did)
        if not s:
            continue

        if show_candidates:
            top3 = cands[:3]
            # Markdown table cell에서 줄바꿈 가능하도록 <br> 사용
            lines = []
            for x in top3:
                sid = int(x.get("docket_id") or 0)
                sc = float(x.get("score") or 0.0)
                nm = _safe_str(x.get("case_name") or "") or f"docket {sid}"
                lines.append(f"{sc:.2f} - {nm} (https://www.courtlistener.com/docket/{sid}/)")
            s.docket_candidates = "<br>".join(lines)

        out.append(s)
        seen.add(did)

    return out


def build_documents_from_docket_ids(docket_ids: List[int], days: int = 3) -> List[CLDocument]:
    """도켓 id 리스트에서 Complaint(우선) 또는 fallback 문서를 수집."""
    docs_out: List[CLDocument] = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    for did in docket_ids:
        if not did:
            continue
        docket = fetch_docket(int(did)) or {}
        case_name = _safe_str(docket.get("case_name") or docket.get("caseName") or "") or "미확인"
        docket_number = _safe_str(docket.get("docket_number") or docket.get("docketNumber") or "") or "미확인"
        court = _safe_str(docket.get("court") or docket.get("court_id") or docket.get("courtId") or "") or "미확인"

        recap_docs = list_recap_documents(int(did))
        if not recap_docs:
            continue

        picked, mode = pick_recap_documents_with_fallback(recap_docs)
        if not picked:
            continue

        for d in picked[:3]:
            doc_type = _safe_str(d.get("document_type") or d.get("documentType") or "")
            doc_number = _safe_str(d.get("document_number") or d.get("documentNumber") or d.get("document_num") or "")
            desc = _safe_str(d.get("description") or "")
            date_filed = _safe_str(d.get("date_filed") or d.get("dateFiled") or "")[:10]
            if not date_filed:
                date_filed = datetime.now(timezone.utc).date().isoformat()

            try:
                dtf = datetime.fromisoformat(date_filed).replace(tzinfo=timezone.utc)
                if dtf < cutoff:
                    continue
            except Exception:
                pass

            document_url = _abs_url(d.get("absolute_url") or d.get("absoluteUrl") or d.get("url") or "")
            pdf_url = _extract_pdf_url(d)
            snippet = ""
            if pdf_url and (pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower()):
                snippet = extract_pdf_text(pdf_url, max_chars=3500)

            p_ex, d_ex = extract_parties_from_caption(snippet) if snippet else ("미확인", "미확인")
            causes = detect_causes(snippet) if snippet else []
            ai_snip = extract_ai_training_snippet(snippet) if snippet else ""

            dt_label = doc_type or ("Complaint" if _is_complaint(d) else "Document")
            if mode == "fallback" and dt_label:
                dt_label = f"FALLBACK: {dt_label}"

            docs_out.append(CLDocument(
                docket_id=int(did),
                docket_number=docket_number,
                case_name=case_name,
                court=court,
                date_filed=date_filed,
                doc_type=dt_label,
                doc_number=doc_number or "미확인",
                description=desc or "미확인",
                document_url=document_url or pdf_url or "",
                pdf_url=pdf_url or "",
                pdf_text_snippet=snippet,
                extracted_plaintiff=p_ex,
                extracted_defendant=d_ex,
                extracted_causes=", ".join(causes) if causes else "미확인",
                extracted_ai_snippet=ai_snip or "",
            ))

    uniq = {}
    for x in docs_out:
        key = (x.docket_id, x.doc_number, x.date_filed, x.document_url)
        uniq[key] = x
    return list(uniq.values())

def _is_key_non_complaint(doc: dict) -> bool:
    """Complaint가 없을 때 보조로 포함할 '핵심 문서' 필터.
    - Motion to Dismiss / TRO / PI / Summary Judgment 등
    - Order / Opinion / Judgment 등
    """
    sd = (_safe_str(doc.get("short_description") or doc.get("shortDescription") or "")).lower()
    desc = (_safe_str(doc.get("description") or doc.get("text") or "")).lower()
    doc_type = (_safe_str(doc.get("document_type") or doc.get("documentType") or "")).lower()
    hay = " ".join([sd, desc, doc_type])
    keys = [
        "motion to dismiss", "motion", "t.r.o", "tro", "temporary restraining", "preliminary injunction",
        "summary judgment", "motion for", "opposition", "reply", "memorandum", "brief",
        "order", "opinion", "judgment", "report and recommendation", "r&r", "recommendation",
        "stipulation", "settlement",
    ]
    return any(k in hay for k in keys)

def pick_recap_documents_with_fallback(recap_docs: list[dict]) -> tuple[list[dict], str]:
    """1) Complaint 우선. 2) 없으면 Motion/Order/Opinion 등 핵심 문서로 fallback.
    반환: (선택된 문서 리스트, 모드 문자열)
    """
    complaint_docs = [d for d in recap_docs if _is_complaint(d)]
    if complaint_docs:
        return complaint_docs, "complaint"
    key_docs = [d for d in recap_docs if _is_key_non_complaint(d)]
    return key_docs, "fallback"



