from sqlalchemy.orm import Session

from app.models.org import Department, DepartmentRegionAssignment, OrgSettings, Region
from app.models.user import User


def resolve_role_to_user(
    role: str,
    db: Session,
    requester_dept_id: str,
    requester_region_id: str | None,
    project_owner_dept_id: str | None = None,
) -> str | None:
    """
    Returns the user_id who holds the given role for this request's org context.
    Returns None when the seat is unassigned; callers fall back to role-name matching.
    """
    if role == "department_head":
        dept = db.get(Department, requester_dept_id)
        if dept and dept.head_user_id:
            return dept.head_user_id
        user = (
            db.query(User)
            .filter(
                User.role == "department_head",
                User.department_id == requester_dept_id,
                User.is_active.is_(True),
            )
            .first()
        )
        return user.id if user else None

    if role == "regional_department_head":
        if not requester_region_id:
            return None
        assignment = (
            db.query(DepartmentRegionAssignment)
            .filter(
                DepartmentRegionAssignment.department_id == requester_dept_id,
                DepartmentRegionAssignment.region_id == requester_region_id,
            )
            .first()
        )
        if assignment and assignment.regional_department_head_user_id:
            return assignment.regional_department_head_user_id
        user = (
            db.query(User)
            .filter(
                User.role == "regional_department_head",
                User.department_id == requester_dept_id,
                User.region_id == requester_region_id,
                User.is_active.is_(True),
            )
            .first()
        )
        return user.id if user else None

    if role == "regional_manager":
        if not requester_region_id:
            return None
        region = db.get(Region, requester_region_id)
        if region and region.regional_manager_user_id:
            return region.regional_manager_user_id
        user = (
            db.query(User)
            .filter(
                User.role == "regional_manager",
                User.region_id == requester_region_id,
                User.is_active.is_(True),
            )
            .first()
        )
        return user.id if user else None

    if role in ("finance_controller", "finance_control", "procurement", "cfo"):
        settings = db.get(OrgSettings, 1)
        if settings:
            seat_map = {
                "finance_controller": settings.finance_controller_user_id,
                "finance_control": settings.finance_control_user_id,
                "procurement": settings.procurement_user_id,
                "cfo": settings.cfo_user_id,
            }
            user_id = seat_map.get(role)
            if user_id:
                return user_id
        user = (
            db.query(User).filter(User.role == role, User.is_active.is_(True)).first()
        )
        return user.id if user else None

    if role == "project_owner":
        dept_id = project_owner_dept_id or requester_dept_id
        dept = db.get(Department, dept_id)
        if dept and dept.project_owner_user_id:
            return dept.project_owner_user_id
        user = (
            db.query(User)
            .filter(
                User.role == "project_owner",
                User.department_id == dept_id,
                User.is_active.is_(True),
            )
            .first()
        )
        return user.id if user else None

    return None
