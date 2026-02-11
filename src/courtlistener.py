from __future__ import annotations

import os
import re
import requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from .pdf_text import extract_pdf_text
from .complaint_parse import (
    detect_causes,
    extract_ai_training_snippet,
    extract_parties_from_caption,
)

BASE = "https://www.courtlistener.com"
SEARCH_URL = BASE + "/api/rest/v4/search/"
DOCKET_URL = BASE + "/api/rest/v4/dockets/{id}/"
RECAP_DOCS_URL = BASE + "/api/rest/v4/recap-documents/"
PARTIES_URL = BASE + "/api/rest/v4/parties/"
DOCKET_ENTRIES_URL = BASE + "/api/rest/v4/docket-entries/"

COMPLAINT_KEYWORDS = [
    "complaint",
    "amended complaint",
    "petition",
    "class action complaint",
]

# =================================================
# Dataclasses
# =================================================

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
    docket_candidates: str = ""


# =================================================
# Utility
# =================================================

def _safe_str(x) -> str:
    return str(x).strip() if x is not None else ""


def _build_court_meta(court_raw: str) -> tuple[str, str]:
    court_raw = _safe_str(court_raw)
    if not court_raw or court_raw == "미확인":
        return "미확인", ""
    return court_raw, f"https://www.courtlistener.com/court/{court_raw}/"


def _headers() -> Dict[str, str]:
    token = os.getenv("COURTLISTENER_TOKEN", "").strip()
    headers = {
        "Accept": "application/json",
        "User-Agent": "ai-lawsuit-monitor/1.3",
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


# =================================================
# Search
# =================================================

def search_recent_documents(query: str, days: int = 3, max_results: int = 20) -> List[dict]:
    data = _get(
        SEARCH_URL,
        params={
            "q": query,
            "type": "r",
            "order_by": "dateFiled desc",
            "page_size": max_results,
        },
    )
    if not data:
        return []

    results = data.get("results", [])
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    filtered = []
    for r in results:
        date_val = _safe_str(r.get("dateFiled") or r.get("date_filed"))
        if date_val:
            try:
                dt = datetime.fromisoformat(date_val[:10]).replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue
            except Exception:
                pass
        filtered.append(r)

    return filtered


def _pick_docket_id(hit: dict) -> Optional[int]:
    for key in ["docket_id", "docketId", "docket"]:
        v = hit.get(key)
        if isinstance(v, int):
            return v
    url = hit.get("absolute_url") or ""
    m = re.search(r"/docket/(\d+)/", url)
    if m:
        return int(m.group(1))
    return None


# =================================================
# Builders
# =================================================

def build_complaint_documents_from_hits(hits: List[dict]) -> List[CLDocument]:
    out: List[CLDocument] = []

    for hit in hits:
        docket_id = _pick_docket_id(hit)
        if not docket_id:
            continue

        docket = _get(DOCKET_URL.format(id=docket_id)) or {}
        case_name = _safe_str(docket.get("case_name")) or "미확인"
        docket_number = _safe_str(docket.get("docket_number")) or "미확인"
        court = _safe_str(docket.get("court")) or "미확인"

        recap = _get(RECAP_DOCS_URL, params={"docket": docket_id}) or {}
        docs = recap.get("results", [])

        for d in docs:
            desc = _safe_str(d.get("description")).lower()
            if not any(k in desc for k in COMPLAINT_KEYWORDS):
                continue

            pdf_url = d.get("filepath_local") or ""
            snippet = extract_pdf_text(pdf_url, max_chars=3000) if pdf_url else ""

            p_ex, d_ex = extract_parties_from_caption(snippet) if snippet else ("미확인", "미확인")
            causes = detect_causes(snippet) if snippet else []
            ai_snip = extract_ai_training_snippet(snippet) if snippet else ""

            out.append(CLDocument(
                docket_id=docket_id,
                docket_number=docket_number,
                case_name=case_name,
                court=court,
                date_filed=_safe_str(d.get("date_filed"))[:10],
                doc_type="Complaint",
                doc_number=_safe_str(d.get("document_number")),
                description=_safe_str(d.get("description")),
                document_url=d.get("absolute_url") or "",
                pdf_url=pdf_url,
                pdf_text_snippet=snippet,
                extracted_plaintiff=p_ex,
                extracted_defendant=d_ex,
                extracted_causes=", ".join(causes) if causes else "미확인",
                extracted_ai_snippet=ai_snip,
            ))

    return out


def build_case_summaries_from_hits(hits: List[dict]) -> List[CLCaseSummary]:
    summaries: List[CLCaseSummary] = []

    for hit in hits:
        docket_id = _pick_docket_id(hit)
        if not docket_id:
            continue

        docket = _get(DOCKET_URL.format(id=docket_id)) or {}

        case_name = _safe_str(docket.get("case_name")) or "미확인"
        docket_number = _safe_str(docket.get("docket_number")) or "미확인"
        court = _safe_str(docket.get("court")) or "미확인"
        court_short_name, court_api_url = _build_court_meta(court)

        date_filed = _safe_str(docket.get("date_filed"))[:10] or "미확인"
        status = "진행중/미확인"

        summaries.append(CLCaseSummary(
            docket_id=docket_id,
            case_name=case_name,
            docket_number=docket_number,
            court=court,
            court_short_name=court_short_name,
            court_api_url=court_api_url,
            date_filed=date_filed,
            status=status,
            judge="미확인",
            magistrate="미확인",
            nature_of_suit="미확인",
            cause="미확인",
            parties="미확인",
            complaint_doc_no="미확인",
            complaint_link="",
            recent_updates="미확인",
            extracted_causes="미확인",
            extracted_ai_snippet="",
        ))

    return summaries
