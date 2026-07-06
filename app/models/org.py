from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    head_user_id = Column(
        String,
        ForeignKey("users.id", use_alter=True, name="fk_dept_head_user_id"),
        nullable=True,
    )
    project_owner_user_id = Column(
        String,
        ForeignKey("users.id", use_alter=True, name="fk_dept_project_owner_user_id"),
        nullable=True,
    )


class Region(Base):
    __tablename__ = "regions"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    regional_manager_user_id = Column(
        String,
        ForeignKey("users.id", use_alter=True, name="fk_region_manager_user_id"),
        nullable=True,
    )


class DepartmentRegionAssignment(Base):
    __tablename__ = "dept_region_assignments"

    id = Column(String, primary_key=True)
    department_id = Column(String, ForeignKey("departments.id"), nullable=False)
    region_id = Column(String, ForeignKey("regions.id"), nullable=False)
    regional_department_head_user_id = Column(
        String, ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("department_id", "region_id", name="uq_dept_region"),
    )


class OrgSettings(Base):
    __tablename__ = "org_settings"

    id = Column(Integer, primary_key=True, default=1)
    finance_controller_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    finance_control_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    procurement_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    cfo_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    md_user_id = Column(String, ForeignKey("users.id"), nullable=True)
