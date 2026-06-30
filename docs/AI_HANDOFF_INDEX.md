# MK-MAP AI Handoff Index

이 폴더는 Codex와 Claude Code가 같은 프로젝트를 이어서 작업하기 위한 인수인계 문서 묶음이다.

## 먼저 읽을 파일

1. `docs/AI_PROJECT_HANDOFF.md`
   - 프로젝트 전체 목적, 현재 상태, 주요 완료 작업, 운영 이슈, 다음 우선순위를 한 번에 본다.

2. `docs/AI_WORKFLOW_AND_STORAGE.md`
   - 데이터 저장 방식, 산출물 경로, API 키/환경변수 관리 원칙, 파이프라인 실행 순서를 본다.

3. `docs/AI_NEXT_ROADMAP.md`
   - 앞으로 해야 할 작업을 우선순위별로 본다.

4. `docs/AI_AGENT_WORKSTYLE.md`
   - Codex가 어떤 방식으로 작업했고, Claude Code가 이어받을 때 지켜야 할 작업 원칙을 본다.

## 앞으로 작업 후 반드시 업데이트할 것

작업자가 Codex든 Claude Code든, 의미 있는 변경을 끝냈으면 아래 파일을 갱신한다.

- 진행상태가 바뀌면 `docs/AI_PROJECT_HANDOFF.md`
- 저장 구조, 실행 명령, 환경변수가 바뀌면 `docs/AI_WORKFLOW_AND_STORAGE.md`
- 다음 작업 목록이 바뀌면 `docs/AI_NEXT_ROADMAP.md`
- 작업 규칙이나 주의사항이 추가되면 `docs/AI_AGENT_WORKSTYLE.md`

## 현재 가장 중요한 미해결 상태

- 로컬 코드와 GitHub CI는 정상이다.
- Railway 공개 서버는 최신 코드가 반영되어 KST 날짜 기준으로 응답한다.
- 하지만 운영 DB에는 2026-07-01 예측/신호 데이터가 아직 들어가지 않아 공개 API의 예측 결과가 비어 있다.
- 원격 admin pipeline 실행에는 Railway `ADMIN_KEY`가 필요하다. 로컬 `.env`에는 현재 `ADMIN_KEY`가 없다.

