"""CRUD de tags de contato (inbox)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import get_current_user
from app.deps import DbSession
from app.models import ContactTag

router = APIRouter(
    prefix="/api/contact-tags",
    tags=["Contact Tags"],
    dependencies=[Depends(get_current_user)],
)

# Espelha a paleta de chips do frontend (lib/api-inbox.ts).
VALID_COLORS = {"blue", "green", "red", "purple", "amber", "pink", "cyan"}


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = "blue"


def _tag_to_dict(t: ContactTag) -> dict:
    return {"id": t.id, "name": t.name, "color": t.color}


@router.get("")
async def list_tags(db: DbSession):
    res = await db.execute(select(ContactTag).order_by(ContactTag.name))
    return [_tag_to_dict(t) for t in res.scalars().all()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tag(data: TagCreate, db: DbSession):
    if data.color not in VALID_COLORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cor inválida. Use uma de: {', '.join(sorted(VALID_COLORS))}",
        )
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Nome da tag não pode ser vazio")

    existing = await db.execute(select(ContactTag).where(ContactTag.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe uma tag com esse nome")

    tag = ContactTag(name=name, color=data.color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return _tag_to_dict(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, db: DbSession):
    tag = await db.get(ContactTag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag não encontrada")
    # Os vínculos em contact_tag_links caem por ON DELETE CASCADE.
    await db.delete(tag)
    await db.commit()
