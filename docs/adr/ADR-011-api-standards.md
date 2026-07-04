# ADR-011. API 표준 — 응답 envelope · RBAC · 버전

- Status: Accepted (점진 적용)
- Date: 2026-07-04

## Context
엔드포인트 73개가 원시 JSON을 반환하고 권한 체크가 분산돼 있다. Bible Vol.3는
표준 응답 `{success,data,meta,error}`, /api/v1 버전, RBAC를 요구한다. 그러나 기존
프론트가 원시 JSON에 의존하므로 일괄 변경은 회귀 위험이 크다.

## Decision
- **표준 envelope**(app/response.py: ok/err/paginated)를 도입하되 **신규·이관 엔드포인트부터** 사용.
  기존 엔드포인트는 프론트 호환 위해 유지, 점진 이관(스트랭글러).
- **RBAC**(app/rbac.py: Role, PERMISSIONS, require_role, require_verified_producer)로 권한 단일화.
  기존 require_user/check_admin은 유지하며 신규는 rbac 사용.
- 버전은 /api/v1 유지. 관리자 API는 X-Admin-Key(별도 게이트).

## Consequences
- 무중단·무회귀로 표준을 확립. 첫 채택: GET /api/v1/items/catalog(envelope).
- 이후 반복에서 도메인별로 엔드포인트를 envelope+rbac로 이관.
