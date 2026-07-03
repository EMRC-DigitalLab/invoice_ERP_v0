from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.auth import UserOut

_camel_cfg = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=to_camel,
)

# ── Response schemas ───────────────────────────────────────────────────────────


class DepartmentOut(BaseModel):
    model_config = _camel_cfg

    id: str
    name: str
    head_user_id: str | None = None
    project_owner_user_id: str | None = None


class RegionOut(BaseModel):
    model_config = _camel_cfg

    id: str
    name: str
    regional_manager_user_id: str | None = None


class DeptRegionAssignmentOut(BaseModel):
    model_config = _camel_cfg

    id: str
    department_id: str
    region_id: str
    regional_department_head_user_id: str | None = None


class OrgSettingsOut(BaseModel):
    model_config = _camel_cfg

    finance_controller_user_id: str | None = None
    finance_control_user_id: str | None = None
    procurement_user_id: str | None = None
    cfo_user_id: str | None = None


# ── Input schemas ──────────────────────────────────────────────────────────────


class OnboardStaffPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    name: str
    email: str
    role: str
    title: str
    department_id: str
    region_id: str | None = None
    is_admin: bool = False


class UpdateStaffPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    role: str | None = None
    title: str | None = None
    department_id: str | None = None
    region_id: str | None = None
    is_admin: bool | None = None


class UpdateDepartmentPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    name: str | None = None
    head_user_id: str | None = None
    project_owner_user_id: str | None = None


class UpdateRegionPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    name: str | None = None
    regional_manager_user_id: str | None = None


class UpsertDeptRegionAssignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    department_id: str
    region_id: str
    regional_department_head_user_id: str | None = None


class UpdateOrgSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    finance_controller_user_id: str | None = None
    finance_control_user_id: str | None = None
    procurement_user_id: str | None = None
    cfo_user_id: str | None = None


# ── Response envelope schemas ──────────────────────────────────────────────────


class MetaOut(BaseModel):
    total: int


class StaffListResponse(BaseModel):
    data: list[UserOut]
    meta: MetaOut


class StaffDetailResponse(BaseModel):
    data: UserOut


class OnboardResult(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    staff: UserOut
    temporary_password: str


class OnboardStaffResponse(BaseModel):
    data: OnboardResult


class DepartmentListResponse(BaseModel):
    data: list[DepartmentOut]
    meta: MetaOut


class DepartmentDetailResponse(BaseModel):
    data: DepartmentOut


class RegionListResponse(BaseModel):
    data: list[RegionOut]
    meta: MetaOut


class RegionDetailResponse(BaseModel):
    data: RegionOut


class AssignmentListResponse(BaseModel):
    data: list[DeptRegionAssignmentOut]
    meta: MetaOut


class AssignmentDetailResponse(BaseModel):
    data: DeptRegionAssignmentOut


class OrgSettingsResponse(BaseModel):
    data: OrgSettingsOut
