from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth import CurrentUser, get_current_user
from app.contact_lists.csv_parser import parse_csv_bytes
from app.deps import DbSession
from app.models import ContactList, ContactListMember

router = APIRouter(
    prefix="/api/contact-lists",
    tags=["Contact Lists"],
    dependencies=[Depends(get_current_user)],
)


class ContactListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    channel_id: Optional[int] = None


class ContactListUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    channel_id: Optional[int] = None


def _list_to_dict(lst: ContactList, member_count: int = 0) -> dict:
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "channel_id": lst.channel_id,
        "created_by": lst.created_by,
        "created_at": lst.created_at.isoformat() if lst.created_at else None,
        "updated_at": lst.updated_at.isoformat() if lst.updated_at else None,
        "member_count": member_count,
    }


@router.get("")
async def list_lists(db: DbSession):
    res = await db.execute(
        select(
            ContactList,
            sql_func.count(ContactListMember.id).label("member_count"),
        )
        .outerjoin(ContactListMember, ContactListMember.list_id == ContactList.id)
        .group_by(ContactList.id)
        .order_by(ContactList.updated_at.desc())
    )
    rows = res.all()
    return [_list_to_dict(lst, mc) for lst, mc in rows]


@router.get("/{list_id}")
async def get_list(list_id: int, db: DbSession):
    lst = await db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lista não encontrada")
    count_res = await db.execute(
        select(sql_func.count(ContactListMember.id)).where(ContactListMember.list_id == list_id)
    )
    return _list_to_dict(lst, count_res.scalar() or 0)


@router.post("", status_code=201)
async def create_list(data: ContactListCreate, db: DbSession, current_user: CurrentUser):
    lst = ContactList(
        name=data.name,
        description=data.description,
        channel_id=data.channel_id,
        created_by=current_user.id,
    )
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    return _list_to_dict(lst, 0)


@router.patch("/{list_id}")
async def update_list(list_id: int, data: ContactListUpdate, db: DbSession):
    lst = await db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lista não encontrada")
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(lst, k, v)
    await db.commit()
    await db.refresh(lst)
    count_res = await db.execute(
        select(sql_func.count(ContactListMember.id)).where(ContactListMember.list_id == list_id)
    )
    return _list_to_dict(lst, count_res.scalar() or 0)


@router.delete("/{list_id}", status_code=204)
async def delete_list(list_id: int, db: DbSession):
    lst = await db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lista não encontrada")
    await db.delete(lst)
    await db.commit()


@router.get("/{list_id}/members")
async def list_members(
    list_id: int,
    db: DbSession,
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    lst = await db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lista não encontrada")

    q = select(ContactListMember).where(ContactListMember.list_id == list_id)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(
            sql_func.lower(ContactListMember.name).like(like)
            | ContactListMember.wa_id.like(like)
        )
    q = q.order_by(ContactListMember.added_at.desc()).limit(limit).offset(offset)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {
        "members": [
            {
                "id": m.id,
                "list_id": m.list_id,
                "wa_id": m.wa_id,
                "name": m.name,
                "custom_vars": m.custom_vars or {},
                "opted_out": m.opted_out,
                "added_at": m.added_at.isoformat() if m.added_at else None,
            }
            for m in rows
        ]
    }


@router.post("/{list_id}/import")
async def import_csv(list_id: int, db: DbSession, file: UploadFile = File(...)):
    lst = await db.get(ContactList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lista não encontrada")

    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo maior que 10 MB")

    result = parse_csv_bytes(raw)
    if not result.rows and result.errors:
        return {
            "list_id": list_id,
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": result.errors,
            "detected_columns": result.detected_columns,
            "total_lines": result.total_lines,
        }

    payload_rows = [
        {
            "list_id": list_id,
            "wa_id": r.wa_id,
            "name": r.name,
            "custom_vars": r.custom_vars,
        }
        for r in result.rows
    ]
    stmt = pg_insert(ContactListMember).values(payload_rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_contact_list_member_list_wa")
    insert_result = await db.execute(stmt)
    await db.commit()

    inserted = insert_result.rowcount or 0
    print(
        f"📥 CSV import lista {list_id}: {inserted} inseridos, {len(payload_rows) - inserted} duplicados, {len(result.errors)} erros",
        flush=True,
    )
    return {
        "list_id": list_id,
        "imported": inserted,
        "skipped_duplicates": len(payload_rows) - inserted,
        "errors": result.errors,
        "detected_columns": result.detected_columns,
        "total_lines": result.total_lines,
    }


@router.delete("/{list_id}/members/{member_id}", status_code=204)
async def remove_member(list_id: int, member_id: int, db: DbSession):
    m = await db.get(ContactListMember, member_id)
    if not m or m.list_id != list_id:
        raise HTTPException(status_code=404, detail="Membro não encontrado")
    await db.delete(m)
    await db.commit()
