# AI Agent Workstyle For MK-MAP

마지막 업데이트: 2026-07-01 KST

이 문서는 Codex와 Claude Code가 같은 기준으로 일하기 위한 작업 스타일 문서다.

## 기본 태도

사용자는 “계속 순차적으로 진행”을 원한다.

따라서 다음처럼 작업한다.

- 물어보지 않아도 되는 것은 묻지 않는다.
- 로컬에서 확인 가능한 것은 직접 확인한다.
- 코드 변경 후 반드시 검증한다.
- 실패하면 원인을 좁히고 고친 뒤 다시 검증한다.
- 커밋/푸시 후 GitHub CI까지 확인한다.
- 민감정보가 필요한 작업은 값을 출력하지 않는다.

## 절대 하면 안 되는 것

- 실제 API 키를 문서나 코드에 적지 않는다.
- 사용자 비밀번호, 이메일, admin key를 커밋하지 않는다.
- `.env`를 커밋하지 않는다.
- 추측한 provider code를 품목 mapping에 넣지 않는다.
- 사용자가 만든 변경을 무단으로 되돌리지 않는다.
- `git reset --hard` 같은 파괴 명령을 쓰지 않는다.

## 검색과 수정 원칙

- 파일 검색은 `rg`를 우선 사용한다.
- 작은 수동 수정은 `apply_patch`를 사용한다.
- 대량 기계 치환이 필요한 경우에만 shell을 사용한다.
- shell 치환을 썼으면 반드시 `py_compile`, `git diff --check`로 확인한다.

## 검증 루틴

작업 단위마다 가능한 범위에서 다음을 수행한다.

```powershell
python scripts\run_smoke_suite.py --timeout-seconds 300
git diff --check
```

백엔드 관련 변경이면:

```powershell
$venv = Join-Path $env:TEMP 'mkmap-ci-venv-312'
$env:DATABASE_URL='sqlite+aiosqlite:///./test_agri.db'
$env:ADMIN_KEY='test-admin-key'
$env:PYTHONPATH=(Join-Path (Get-Location) 'backend')
& (Join-Path $venv 'Scripts\python.exe') -m pytest backend\tests\test_pipeline.py backend\tests\test_api.py -q
```

비밀값 검색:

```powershell
rg -n "<known-secret-prefix-or-private-identifier>" backend map_viewer scripts docs config mkmap_meta metadata --glob '!*.db' --glob '!*.pyc' --glob '!__pycache__/**'
```

## 커밋과 CI

의미 있는 작업 단위가 검증되면 커밋한다.

예:

```powershell
git add <files>
git commit -m "Short clear message"
git push origin main
```

푸시 후 GitHub Actions 확인:

```powershell
$uri = 'https://api.github.com/repos/kangs19/mkmap/actions/runs?branch=main&per_page=5'
$headers = @{ 'User-Agent' = 'codex' }
$res = Invoke-RestMethod -Uri $uri -Headers $headers
$res.workflow_runs | Select-Object id,name,head_sha,status,conclusion,created_at,html_url | ConvertTo-Json -Depth 4
```

새 run id가 있으면 완료까지 polling한다.

## 제공자 API 오류 해석

공공데이터 API는 자주 다음을 반환한다.

- `NO_DATA`
- `DB_ERROR`
- `HTTP_403`
- 요청 날짜 자료 없음
- timeout

중요:

- 이들은 항상 코드 실패가 아니다.
- 진단에서는 `no_data`, `api_error`, `http_error`로 분리한다.
- pipeline은 가능한 한 한 provider 오류 때문에 전체가 멈추지 않게 한다.

## 품목 mapping 원칙

정확한 provider code가 확인되지 않으면 mapping하지 않는다.

특히 AT market settlement는 품목명이 섞일 수 있다.

나쁜 예:

- 배추 검색 결과에 얼갈이/양배추가 섞임
- 무 검색 결과에 열무/다른 품목이 섞임

좋은 방식:

- 공식 코드표 확인
- endpoint를 정확한 대/중/소분류 코드로 필터링
- sample raw의 품목명 확인
- live test script로 검증

## 날짜 기준

서비스는 한국 사용자 기준이므로 KST가 기준이다.

backend에서는 `date.today()` 대신 다음을 우선 사용한다.

```python
from app.timezone import kst_today, kst_now
```

Railway 서버는 UTC일 수 있으므로 public API와 scheduler는 반드시 KST 기준이어야 한다.

## 문서 업데이트 규칙

작업 후 다음 파일을 갱신한다.

- `docs/AI_PROJECT_HANDOFF.md`
- `docs/AI_WORKFLOW_AND_STORAGE.md`
- `docs/AI_NEXT_ROADMAP.md`
- `docs/AI_AGENT_WORKSTYLE.md`

변경이 작더라도 다음 중 하나가 바뀌면 문서 업데이트가 필요하다.

- 실행 명령
- 저장 경로
- 환경변수
- 운영 상태
- 다음 작업 우선순위
- provider API 해석

## 사용자 지정 작업 준수사항 (2026-07-01 추가)

1. **git pull/fetch 먼저**: 작업 전 `git status` 확인, 다른 작업자 변경 되돌리지 말 것
2. **시작 전 문서 읽기**: `AI_HANDOFF_INDEX.md` → `AI_PROJECT_HANDOFF.md` → `AI_WORKFLOW_AND_STORAGE.md` → `AI_NEXT_ROADMAP.md` → `AI_AGENT_WORKSTYLE.md`
3. **우선순위**: 운영 DB 완성 → health/admin 확인 → pipeline 실행 → public API 검증
4. **민감정보**: 키 값 출력 금지, "configured/present/length"만 언급
5. **import 안전장치**: forecasts 5개 필수, signals 0이면 실패, push 후 verifier 필수
6. **검증 명령**:
   - `python scripts\run_smoke_suite.py --timeout-seconds 300`
   - `python scripts\verify_public_api_outputs.py --expected-date YYYY-MM-DD`
   - `python -m py_compile ...` + `git diff --check`
7. **작업 후 문서 업데이트**: `AI_PROJECT_HANDOFF.md`, `AI_NEXT_ROADMAP.md` 필수 갱신
8. **커밋**: 검증 통과 후 소단위 commit → push → GitHub Actions CI 성공 확인
9. **주의사항**: `KOSIS_PRODUCTION_TBL_ID` 전역 env 금지, KMA 일부 오류는 provider 상태 문제

## 현재 작업자의 다음 초점 (2026-07-01 업데이트)

완료됨:
- Railway Variables 설정, production 모드 확인
- 운영 DB import (signals 85, forecasts 5)
- KAMIS SSL 오류 수정 (커밋 6a247c4)

현재 진행:
- 원격 파이프라인 재실행 (KAMIS SSL fix 적용 후)

다음 우선순위:
1. 원격 파이프라인 성공 확인 → daily_prices DB 반영 여부 확인
2. `verify_public_api_outputs.py` 8/8 통과 달성 (현재 7/8)
3. 데이터 정확도: at_wholesale_norm 공백 58% 문제
4. AT settlement 배추/무 코드 매핑 (API 502 복구 후)

