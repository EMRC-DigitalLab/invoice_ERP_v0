import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, get_password_hash
from app.models.org import Department, DepartmentRegionAssignment, OrgSettings, Region
from app.models.request import ApprovalStep
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.org import (
    AssignmentDetailResponse,
    AssignmentListResponse,
    CreateDepartmentPayload,
    CreateRegionPayload,
    DepartmentDetailResponse,
    DepartmentListResponse,
    DepartmentOut,
    DeptRegionAssignmentOut,
    MetaOut,
    OnboardResult,
    OnboardStaffPayload,
    OnboardStaffResponse,
    OrgSettingsOut,
    OrgSettingsResponse,
    RegionDetailResponse,
    RegionListResponse,
    RegionOut,
    StaffDetailResponse,
    StaffListResponse,
    UpdateDepartmentPayload,
    UpdateOrgSettings,
    UpdateRegionPayload,
    UpdateStaffPayload,
    UpsertDeptRegionAssignment,
)
from app.services.email import send_welcome_email

router = APIRouter(prefix="/org", tags=["org"])

_ADMIN_ONLY = "You are not authorised to manage the organisation directory."


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_ADMIN_ONLY)


# ── Staff ──────────────────────────────────────────────────────────────────────


@router.get("/staff", response_model=StaffListResponse)
def list_staff(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    staff = db.query(User).filter(User.is_active.is_(True)).order_by(User.name).all()
    items = [UserOut.model_validate(u) for u in staff]
    return StaffListResponse(data=items, meta=MetaOut(total=len(items)))


@router.post(
    "/staff", status_code=status.HTTP_201_CREATED, response_model=OnboardStaffResponse
)
def onboard_staff(
    payload: OnboardStaffPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=409, detail="A staff member with this email already exists."
        )

    # Org-wide singular seats (CFO, MD, etc.) often aren't tied to a department.
    dept_name = "—"
    if payload.department_id:
        dept = db.get(Department, payload.department_id)
        if dept is None:
            raise HTTPException(status_code=400, detail="Department not found.")
        dept_name = dept.name

    initial_password = secrets.token_urlsafe(12)
    title = (payload.title or "").strip() or payload.role.replace("_", " ").title()
    user = User(
        id=uuid.uuid4().hex,
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(initial_password),
        role=payload.role,
        title=title,
        department=dept_name,
        department_id=payload.department_id or None,
        region_id=payload.region_id or None,
        is_admin=payload.is_admin,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    try:
        send_welcome_email(
            to=user.email,
            name=user.name,
            initial_password=initial_password,
            login_link=f"{settings.FRONTEND_URL}/login",
        )
    except Exception:  # noqa: BLE001 — the account is already created; don't fail onboarding over a notification email
        pass

    return OnboardStaffResponse(
        data=OnboardResult(
            staff=UserOut.model_validate(user),
            initial_password=initial_password,
        )
    )


@router.patch("/staff/{user_id}", response_model=StaffDetailResponse)
def update_staff(
    user_id: str,
    payload: UpdateStaffPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff member not found.")

    updates = payload.model_dump(exclude_unset=True)

    if "email" in updates:
        new_email = updates["email"].strip().lower()
        if db.query(User).filter(User.email == new_email, User.id != user_id).first():
            raise HTTPException(
                status_code=409, detail="A staff member with this email already exists."
            )
        updates["email"] = new_email

    if "name" in updates:
        updates["name"] = updates["name"].strip()

    if "region_id" in updates:
        # "" from the "No region" option means clear the seat — storing "" against
        # a foreign key (instead of NULL) would violate the FK constraint.
        updates["region_id"] = updates["region_id"] or None

    if "department_id" in updates:
        updates["department_id"] = updates["department_id"] or None
        if updates["department_id"]:
            dept = db.get(Department, updates["department_id"])
            if dept is None:
                raise HTTPException(status_code=400, detail="Department not found.")
            user.department = dept.name
        else:
            # Org-wide singular seats (CFO, MD, etc.) aren't tied to a department.
            user.department = "—"

    for field, value in updates.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return StaffDetailResponse(data=UserOut.model_validate(user))


@router.delete("/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivates a staff member — a soft delete, not a hard row delete.
    Requests/audit entries this person is attached to reference their name and
    role directly, so history stays intact and readable even after this.
    Also strips them from every seat (org-wide, department, region) so they
    stop being resolvable as an approver anywhere on the dashboard."""
    _require_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="You cannot remove your own account."
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Staff member not found.")

    pending_forward = (
        db.query(ApprovalStep)
        .filter(
            ApprovalStep.assigned_user_id == user_id,
            ApprovalStep.status == "pending",
        )
        .first()
    )
    if pending_forward is not None:
        raise HTTPException(
            status_code=409,
            detail="This person has a pending approval forwarded to them — reassign or resolve it before removing them.",
        )

    user.is_active = False

    for dept in db.query(Department).filter(
        (Department.head_user_id == user_id)
        | (Department.project_owner_user_id == user_id)
    ):
        if dept.head_user_id == user_id:
            dept.head_user_id = None
        if dept.project_owner_user_id == user_id:
            dept.project_owner_user_id = None

    for region in db.query(Region).filter(Region.regional_manager_user_id == user_id):
        region.regional_manager_user_id = None

    for assignment in db.query(DepartmentRegionAssignment).filter(
        DepartmentRegionAssignment.regional_department_head_user_id == user_id
    ):
        assignment.regional_department_head_user_id = None

    org_settings = db.get(OrgSettings, 1)
    if org_settings is not None:
        for field in (
            "finance_controller_user_id",
            "finance_control_user_id",
            "procurement_user_id",
            "cfo_user_id",
            "md_user_id",
            "cfo_letters_uploader_id",
        ):
            if getattr(org_settings, field) == user_id:
                setattr(org_settings, field, None)

    db.commit()


# ── Departments ────────────────────────────────────────────────────────────────


@router.get("/departments", response_model=DepartmentListResponse)
def list_departments(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    depts = db.query(Department).order_by(Department.name).all()
    items = [DepartmentOut.model_validate(d) for d in depts]
    return DepartmentListResponse(data=items, meta=MetaOut(total=len(items)))


@router.post(
    "/departments",
    status_code=status.HTTP_201_CREATED,
    response_model=DepartmentDetailResponse,
)
def create_department(
    payload: CreateDepartmentPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    dept = Department(
        id=uuid.uuid4().hex,
        name=payload.name,
        head_user_id=payload.head_user_id,
        project_owner_user_id=payload.project_owner_user_id,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return DepartmentDetailResponse(data=DepartmentOut.model_validate(dept))


@router.patch("/departments/{dept_id}", response_model=DepartmentDetailResponse)
def update_department(
    dept_id: str,
    payload: UpdateDepartmentPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dept, field, value)

    db.commit()
    db.refresh(dept)
    return DepartmentDetailResponse(data=DepartmentOut.model_validate(dept))


# ── Regions ────────────────────────────────────────────────────────────────────


@router.get("/regions", response_model=RegionListResponse)
def list_regions(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    regions = db.query(Region).order_by(Region.name).all()
    items = [RegionOut.model_validate(r) for r in regions]
    return RegionListResponse(data=items, meta=MetaOut(total=len(items)))


@router.post(
    "/regions",
    status_code=status.HTTP_201_CREATED,
    response_model=RegionDetailResponse,
)
def create_region(
    payload: CreateRegionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    region = Region(
        id=uuid.uuid4().hex,
        name=payload.name,
        regional_manager_user_id=payload.regional_manager_user_id,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return RegionDetailResponse(data=RegionOut.model_validate(region))


@router.patch("/regions/{region_id}", response_model=RegionDetailResponse)
def update_region(
    region_id: str,
    payload: UpdateRegionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    region = db.get(Region, region_id)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(region, field, value)

    db.commit()
    db.refresh(region)
    return RegionDetailResponse(data=RegionOut.model_validate(region))


# ── Dept-Region Assignments ────────────────────────────────────────────────────


@router.get("/dept-region-assignments", response_model=AssignmentListResponse)
def list_assignments(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    assignments = db.query(DepartmentRegionAssignment).all()
    items = [DeptRegionAssignmentOut.model_validate(a) for a in assignments]
    return AssignmentListResponse(data=items, meta=MetaOut(total=len(items)))


@router.post("/dept-region-assignments", response_model=AssignmentDetailResponse)
def upsert_assignment(
    payload: UpsertDeptRegionAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    existing = (
        db.query(DepartmentRegionAssignment)
        .filter(
            DepartmentRegionAssignment.department_id == payload.department_id,
            DepartmentRegionAssignment.region_id == payload.region_id,
        )
        .first()
    )

    if existing:
        existing.regional_department_head_user_id = (
            payload.regional_department_head_user_id
        )
        db.commit()
        db.refresh(existing)
        return AssignmentDetailResponse(
            data=DeptRegionAssignmentOut.model_validate(existing)
        )

    assignment = DepartmentRegionAssignment(
        id=uuid.uuid4().hex,
        department_id=payload.department_id,
        region_id=payload.region_id,
        regional_department_head_user_id=payload.regional_department_head_user_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return AssignmentDetailResponse(
        data=DeptRegionAssignmentOut.model_validate(assignment)
    )


# ── Org Settings ───────────────────────────────────────────────────────────────


@router.get("/settings", response_model=OrgSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_settings = db.get(OrgSettings, 1)
    if org_settings is None:
        return OrgSettingsResponse(data=OrgSettingsOut())
    return OrgSettingsResponse(data=OrgSettingsOut.model_validate(org_settings))


@router.patch("/settings", response_model=OrgSettingsResponse)
def update_settings(
    payload: UpdateOrgSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    org_settings = db.get(OrgSettings, 1)
    if org_settings is None:
        org_settings = OrgSettings(id=1)
        db.add(org_settings)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org_settings, field, value)

    db.commit()
    db.refresh(org_settings)
    return OrgSettingsResponse(data=OrgSettingsOut.model_validate(org_settings))
