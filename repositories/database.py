from typing import Optional
from sqlalchemy import create_engine, String, Integer, Float, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# Connection string points to an existing database; no automatic creation here
DB_URL = "sqlite:///data/credit.db"

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


class CreditProfileORM(Base):
    __tablename__ = "credit_profiles"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Payment history (35%)
    late_30: Mapped[int] = mapped_column(Integer, default=0)
    late_60: Mapped[int] = mapped_column(Integer, default=0)
    late_90p: Mapped[int] = mapped_column(Integer, default=0)
    has_collection: Mapped[bool] = mapped_column(Boolean, default=False)
    has_bankruptcy: Mapped[bool] = mapped_column(Boolean, default=False)
    months_since_last_delinquency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Amounts owed / utilization (30%)
    revolving_utilization: Mapped[float] = mapped_column(Float, default=0.0)
    installment_balance_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    total_accounts: Mapped[int] = mapped_column(Integer, default=5)

    # Length of history (15%)
    age_oldest_acct_years: Mapped[float] = mapped_column(Float, default=6.0)
    avg_age_years: Mapped[float] = mapped_column(Float, default=3.0)

    # New credit (10%)
    hard_inquiries_12m: Mapped[int] = mapped_column(Integer, default=0)
    new_accounts_12m: Mapped[int] = mapped_column(Integer, default=0)

    # Credit mix (10%)
    has_mortgage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_installment: Mapped[bool] = mapped_column(Boolean, default=True)
    has_revolving: Mapped[bool] = mapped_column(Boolean, default=True)
    has_student_or_auto: Mapped[bool] = mapped_column(Boolean, default=False)


# Do NOT auto-create tables; assume schema already exists

# Conversion helpers live here to avoid circular deps
from services.scoring import CreditProfile  # noqa: E402


def orm_to_dc(orm: CreditProfileORM) -> CreditProfile:
    return CreditProfile(
        late_30=orm.late_30,
        late_60=orm.late_60,
        late_90p=orm.late_90p,
        has_collection=orm.has_collection,
        has_bankruptcy=orm.has_bankruptcy,
        months_since_last_delinquency=orm.months_since_last_delinquency,
        revolving_utilization=orm.revolving_utilization,
        installment_balance_ratio=orm.installment_balance_ratio,
        total_accounts=orm.total_accounts,
        age_oldest_acct_years=orm.age_oldest_acct_years,
        avg_age_years=orm.avg_age_years,
        hard_inquiries_12m=orm.hard_inquiries_12m,
        new_accounts_12m=orm.new_accounts_12m,
        has_mortgage=orm.has_mortgage,
        has_installment=orm.has_installment,
        has_revolving=orm.has_revolving,
        has_student_or_auto=orm.has_student_or_auto,
    )


def dc_to_orm(user_id: str, dc: CreditProfile, obj: Optional[CreditProfileORM] = None) -> CreditProfileORM:
    if obj is None:
        obj = CreditProfileORM(user_id=user_id)
    obj.late_30 = dc.late_30
    obj.late_60 = dc.late_60
    obj.late_90p = dc.late_90p
    obj.has_collection = dc.has_collection
    obj.has_bankruptcy = dc.has_bankruptcy
    obj.months_since_last_delinquency = dc.months_since_last_delinquency
    obj.revolving_utilization = dc.revolving_utilization
    obj.installment_balance_ratio = dc.installment_balance_ratio
    obj.total_accounts = dc.total_accounts
    obj.age_oldest_acct_years = dc.age_oldest_acct_years
    obj.avg_age_years = dc.avg_age_years
    obj.hard_inquiries_12m = dc.hard_inquiries_12m
    obj.new_accounts_12m = dc.new_accounts_12m
    obj.has_mortgage = dc.has_mortgage
    obj.has_installment = dc.has_installment
    obj.has_revolving = dc.has_revolving
    obj.has_student_or_auto = dc.has_student_or_auto
    return obj
