# AI Lawsuit Monitor (CourtListener RECAP Complaint Extractor)

최근 3일 내 "AI 모델 학습을 위한 무단/불법 데이터 사용" 관련 소송/업데이트를
- CourtListener(=RECAP Archive)에서 **도켓 + RECAP 문서(특히 Complaint)**를 우선 수집하고,
- 뉴스(RSS)로 보강하여

GitHub Issue에 댓글로 누적하고 Slack으로 요약을 발송합니다.

## 핵심 기능(추가됨: B - Complaint 정밀 추출)
- CourtListener 검색 결과에서 **도켓(docket) 식별**
- 도켓에 연결된 **RECAP 문서 목록 조회**
- 문서 유형이 **Complaint / Amended Complaint / Petition** 등인 항목을 우선 선택
- 가능하면 PDF를 내려받아 **초반 텍스트 일부를 추출**해
  - `소송이유`(자동 요약용 스니펫)
  - `히스토리`(최근 제출 문서 목록 일부)
  를 더 정확하게 구성

> 주의: RECAP은 "공개된 문서만" 존재합니다. 어떤 사건은 RECAP 문서가 없을 수 있으며,
> 그 경우 CourtListener 단계는 힌트만 남기고 뉴스(RSS)로 폴백합니다.

## GitHub Secrets 설정
Repository → Settings → Secrets and variables → Actions → New repository secret

- `GH_TOKEN` (필수): repo 권한 GitHub Personal Access Token (scope: `repo`)
- `SLACK_WEBHOOK_URL` (필수): Slack Incoming Webhook URL
- `COURTLISTENER_TOKEN` (권장): CourtListener API 토큰 (v4 API 인증 필요 가능)

## 커스터마이징
- `src/queries.py`에서 키워드 조정
- `data/known_cases.yml`에 사건 매핑 추가

## 실행
- GitHub Actions: 매시간 정각(UTC)
- 수동 실행: Actions → hourly-monitor → Run workflow


## 균형형 쿼리 튜닝 적용
- CourtListener Search에 `type=r`, `available_only=on`, `order_by=entry_date_filed desc`를 적용해 RECAP 문서(도켓/문서) 중심으로 최신 항목을 우선 수집합니다.


## 추가: 소송번호(도켓) 기반 확장 필드
- 접수일(Date Filed), 상태(Open/Closed), 담당 판사/치안판사, Nature of Suit(NOS), Cause(법률 조항), Parties roster, Complaint 문서번호/링크, 최근 도켓 업데이트 3건을 RECAP 도켓에서 자동 추출합니다.


## Actions 권한/로그 개선
- workflow에 `permissions: issues: write`를 추가해 PAT 없이도 이슈 댓글 업로드가 가능하도록 했습니다.
- Actions 로그에 리포트 본문 일부를 출력하고 `tee run_output.log`로 로그 파일도 남깁니다.


## 일자별 이슈 생성
- 매 실행 결과는 **당일(Asia/Seoul) 날짜가 포함된 이슈**에 누적됩니다.
- 이슈 제목 형식: `AI 불법/무단 학습데이터 소송 모니터링 (YYYY-MM-DD)`
- 필요 시 기본 제목은 `ISSUE_TITLE_BASE` 환경변수로 변경할 수 있습니다.


## 이전 날짜 이슈 자동 Close
- 매일 새 날짜 이슈를 생성한 뒤, 같은 라벨을 가진 이전 날짜의 열린 이슈들을 자동으로 Close 처리합니다.
- 제목 형식이 `기본제목 (YYYY-MM-DD)`인 이슈만 대상이며, 다른 이슈는 닫지 않습니다.


## 자동 Close 시 마무리 코멘트
- 이전 날짜 이슈를 닫기 전에 아래 코멘트를 자동으로 남깁니다.
  - `이 이슈는 다음 날짜 리포트 생성으로 자동 종료되었습니다.`


## 이슈 제목 형식 (KST)
- 이슈 제목: `AI 불법/무단 학습데이터 소송 모니터링 (YYYY-MM-DD HH:MM)`
- 시간은 **KST(Asia/Seoul)** 기준입니다.
- 새 이슈가 생성되면 이전 이슈에 `다음 리포트` 링크 코멘트를 남긴 뒤 자동 Close 합니다.


## 변경: 하루 1개 이슈 + 실행시각은 본문에 기록
- 이슈 제목은 **일자 기준 1개**로 생성됩니다: `AI 불법/무단 학습데이터 소송 모니터링 (YYYY-MM-DD)`
- 매 실행(매시간) 결과는 같은 날짜 이슈에 댓글로 누적되며, 댓글 상단에 `실행 시각(KST)`가 포함됩니다.


## RECAP 보조 모드(Fallback)
- 최근 3일 내 해당 키워드로 RECAP 문서를 찾되, **Complaint가 0건이면** Motion/Order/Opinion/Judgment 등 핵심 문서를 보조로 수집합니다.
- 보조 모드로 수집된 문서는 리포트의 문서유형에 `FALLBACK:` 접두사가 붙습니다.
