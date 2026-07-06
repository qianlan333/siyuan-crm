from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GrowthProgram(BaseModel):
    program_key: str
    program_type: str
    title: str = ""
    status: str = ""
    owner_userid: str = ""
    member_count: int = 0
    active_member_count: int = 0
    task_count: int = 0
    last_activity_at: datetime | None = None
    source_table: str
    source_id: str


class GrowthProgramList(BaseModel):
    ok: bool = True
    items: list[GrowthProgram] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0


class GrowthMember(BaseModel):
    program_key: str
    unionid: str
    current_stage: str = ""
    status: str = ""
    owner_userid: str = ""
    last_touch_at: datetime | None = None
    next_task_at: datetime | None = None
    source_table: str
    source_id: str


class GrowthMemberList(BaseModel):
    ok: bool = True
    items: list[GrowthMember] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0


class GrowthTask(BaseModel):
    task_key: str
    program_key: str = ""
    task_type: str = ""
    status: str = ""
    owner_userid: str = ""
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    target_unionid: str = ""
    target_count: int = 0
    trace_id: str = ""
    source_table: str
    source_id: str


class GrowthTaskList(BaseModel):
    ok: bool = True
    items: list[GrowthTask] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0


class GrowthTouchpoint(BaseModel):
    touchpoint_key: str
    program_key: str = ""
    unionid: str = ""
    touchpoint_type: str = ""
    status: str = ""
    occurred_at: datetime | None = None
    trace_id: str = ""
    source_table: str
    source_id: str


class GrowthTouchpointList(BaseModel):
    ok: bool = True
    items: list[GrowthTouchpoint] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0
