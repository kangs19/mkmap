"""커뮤니티 — 지역 × 품목 댓글 + 우리지역 평가(현장 제보).

원칙 (docs/MKMAP_2.0_PLAN.md §18):
- 커뮤니티는 자유게시판이 아니라 "지역 × 품목" 기반
- 사용자 데이터는 현장 참고자료이며 AI 모델을 변경하지 않음
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.community import User, CommunityComment, FieldReport
from app.routers.auth_user import require_user, get_current_user

router = APIRouter(prefix="/api/v1/community", tags=["community"])

_REPORT_HIDE_THRESHOLD = 5  # 신고 5회 이상이면 숨김


def _comment_out(c: CommunityComment, my_id: int | None = None) -> dict:
    role_label = {"general": "일반", "farmer": "인증 농부", "trader": "유통인", "admin": "관리자"}.get(c.role, c.role)
    return {
        "id": c.id,
        "item_code": c.item_code,
        "region": c.region,
        "nickname": c.nickname,
        "role": c.role,
        "role_label": role_label,
        "content": "삭제된 댓글입니다." if c.is_deleted else c.content,
        "parent_id": c.parent_id,
        "likes": c.likes,
        "is_deleted": c.is_deleted,
        "is_mine": (my_id is not None and c.user_id == my_id),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── 댓글 ─────────────────────────────────────────────────
class CommentIn(BaseModel):
    item_code: str = Field(max_length=30)
    region: str = Field(default="전국", max_length=50)
    content: str = Field(min_length=1, max_length=1000)
    parent_id: int | None = None


@router.get("/comments")
async def list_comments(
    item_code: str,
    region: str = "전국",
    limit: int = 50,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    me = await get_current_user(request, db) if request else None
    rows = (await db.execute(
        select(CommunityComment)
        .where(
            CommunityComment.item_code == item_code,
            CommunityComment.region == region,
            CommunityComment.reports < _REPORT_HIDE_THRESHOLD,
            CommunityComment.is_deleted == False,  # noqa: E712
        )
        .order_by(desc(CommunityComment.created_at))
        .limit(min(limit, 100))
    )).scalars().all()
    total = (await db.execute(
        select(sqlfunc.count()).select_from(CommunityComment).where(
            CommunityComment.item_code == item_code,
            CommunityComment.region == region,
            CommunityComment.is_deleted == False,  # noqa: E712
        )
    )).scalar()
    return {
        "item_code": item_code,
        "region": region,
        "total": total,
        "comments": [_comment_out(c, me.id if me else None) for c in rows],
    }


@router.post("/comments")
async def create_comment(body: CommentIn, request: Request, db: AsyncSession = Depends(get_db)):
    user = await require_user(request, db)
    if body.parent_id:
        parent = (await db.execute(
            select(CommunityComment).where(CommunityComment.id == body.parent_id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail={"error": "parent_not_found"})
    c = CommunityComment(
        item_code=body.item_code,
        region=body.region,
        user_id=user.id,
        nickname=user.nickname,
        # 농부·유통인 배지는 인증 완료 시에만 표시
        role=user.role if (user.role in ("general", "admin") or user.farmer_verified) else "general",
        content=body.content,
        parent_id=body.parent_id,
    )
    db.add(c)
    user.trust_score = (user.trust_score or 0) + 1  # 활동 점수
    await db.commit()
    await db.refresh(c)
    return {"comment": _comment_out(c, user.id)}


@router.delete("/comments/{comment_id}")
async def delete_comment(comment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    user = await require_user(request, db)
    c = (await db.execute(select(CommunityComment).where(CommunityComment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if c.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "본인 댓글만 삭제할 수 있습니다."})
    c.is_deleted = True
    await db.commit()
    return {"ok": True}


@router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await require_user(request, db)
    c = (await db.execute(select(CommunityComment).where(CommunityComment.id == comment_id))).scalar_one_or_none()
    if not c or c.is_deleted:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    c.likes = (c.likes or 0) + 1
    await db.commit()
    return {"ok": True, "likes": c.likes}


@router.post("/comments/{comment_id}/report")
async def report_comment(comment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    await require_user(request, db)
    c = (await db.execute(select(CommunityComment).where(CommunityComment.id == comment_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    c.reports = (c.reports or 0) + 1
    await db.commit()
    return {"ok": True}


# ── 우리지역 평가 (현장 제보) ─────────────────────────────
class FieldReportIn(BaseModel):
    item_code: str = Field(max_length=30)
    region: str = Field(min_length=1, max_length=50)
    growth: str          # good | normal | bad
    pest: str            # none | some | severe
    shipment: str        # up | normal | down
    weather_damage: str | None = Field(default=None, max_length=100)  # "폭염,호우"
    price_feeling: str   # up | same | down
    comment: str | None = Field(default=None, max_length=300)


_ALLOWED = {
    "growth": {"good", "normal", "bad"},
    "pest": {"none", "some", "severe"},
    "shipment": {"up", "normal", "down"},
    "price_feeling": {"up", "same", "down"},
}


@router.post("/field-reports")
async def create_field_report(body: FieldReportIn, request: Request, db: AsyncSession = Depends(get_db)):
    user = await require_user(request, db)
    if user.role == "admin" or (user.role in ("farmer", "trader") and user.farmer_verified):
        pass
    else:
        raise HTTPException(status_code=403, detail={
            "error": "farmer_only",
            "message": "우리지역 평가는 휴대폰 인증을 마친 농부·유통인 회원만 등록할 수 있습니다.",
        })
    for field, allowed in _ALLOWED.items():
        if getattr(body, field) not in allowed:
            raise HTTPException(status_code=400, detail={"error": "invalid_value", "field": field})

    # 같은 사용자·지역·품목 하루 1회
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    dup = (await db.execute(
        select(FieldReport).where(
            FieldReport.user_id == user.id,
            FieldReport.item_code == body.item_code,
            FieldReport.region == body.region,
            FieldReport.created_at >= today_start,
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail={"error": "already_reported", "message": "오늘은 이미 이 지역을 평가하셨습니다."})

    r = FieldReport(
        item_code=body.item_code, region=body.region,
        user_id=user.id, nickname=user.nickname,
        growth=body.growth, pest=body.pest, shipment=body.shipment,
        weather_damage=body.weather_damage, price_feeling=body.price_feeling,
        comment=body.comment,
    )
    db.add(r)
    user.trust_score = (user.trust_score or 0) + 3
    await db.commit()
    return {"ok": True}


@router.get("/field-reports/summary")
async def field_report_summary(
    item_code: str,
    region: str | None = None,
    days: int = 14,
    db: AsyncSession = Depends(get_db),
):
    """최근 N일 현장 제보 집계 — AI와 분리된 '현장 신호' 표시용"""
    since = datetime.utcnow() - timedelta(days=min(days, 90))
    q = select(FieldReport).where(FieldReport.item_code == item_code, FieldReport.created_at >= since)
    if region:
        q = q.where(FieldReport.region == region)
    rows = (await db.execute(q.order_by(desc(FieldReport.created_at)).limit(500))).scalars().all()

    def _count(field: str) -> dict:
        out: dict[str, int] = {}
        for r in rows:
            v = getattr(r, field)
            if v:
                out[v] = out.get(v, 0) + 1
        return out

    damage: dict[str, int] = {}
    for r in rows:
        for d in (r.weather_damage or "").split(","):
            d = d.strip()
            if d:
                damage[d] = damage.get(d, 0) + 1

    recent = [
        {"region": r.region, "nickname": r.nickname, "growth": r.growth, "pest": r.pest,
         "shipment": r.shipment, "price_feeling": r.price_feeling, "comment": r.comment,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows[:10]
    ]
    return {
        "item_code": item_code,
        "region": region,
        "days": days,
        "report_count": len(rows),
        "reporter_count": len({r.user_id for r in rows}),
        "growth": _count("growth"),
        "pest": _count("pest"),
        "shipment": _count("shipment"),
        "price_feeling": _count("price_feeling"),
        "weather_damage": damage,
        "recent": recent,
        "note": "현장 제보는 참고용 현장 신호이며 AI 예측에는 반영되지 않습니다.",
    }
