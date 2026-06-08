from __future__ import annotations

from pydantic import BaseModel, Field


class ResolvePersonIdentityRequest(BaseModel):
    external_userid: str | None = None
    mobile: str | None = None
    openid: str | None = None
    unionid: str | None = None


class ContactPoint(BaseModel):
    type: str
    value: str
    verified: bool = False


class IdentityResolution(BaseModel):
    person_id: str | None
    external_userid: str | None
    mobile: str | None
    openid: str | None = None
    unionid: str | None = None
    binding_status: str = Field(default="unknown")
    owner_userid: str | None = None
    contact_points: list[ContactPoint] = Field(default_factory=list)
