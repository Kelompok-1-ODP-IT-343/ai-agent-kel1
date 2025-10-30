from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, Union
import random
import hashlib

# ================== DOMAIN MODEL (Dataclass) ==================
@dataclass
class CreditProfile:
    # Payment history (35%)
    late_30: int = 0
    late_60: int = 0
    late_90p: int = 0
    has_collection: bool = False
    has_bankruptcy: bool = False
    months_since_last_delinquency: Optional[int] = None

    # Amounts owed / utilization (30%)
    revolving_utilization: float = 0.0  # 0.0–1.0
    installment_balance_ratio: float = 0.0  # 0.0–1.0
    total_accounts: int = 5

    # Length of history (15%)
    age_oldest_acct_years: float = 6.0
    avg_age_years: float = 3.0

    # New credit (10%)
    hard_inquiries_12m: int = 0
    new_accounts_12m: int = 0

    # Credit mix (10%)
    has_mortgage: bool = False
    has_installment: bool = True
    has_revolving: bool = True
    has_student_or_auto: bool = False

# ================== SCORING HELPERS ==================

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_payment_history(p: CreditProfile) -> float:
    s = 100.0
    s -= p.late_30 * 3.0
    s -= p.late_60 * 7.0
    s -= p.late_90p * 15.0
    if p.has_collection:
        s -= 20.0
    if p.has_bankruptcy:
        s -= 40.0
    if p.months_since_last_delinquency is not None:
        s += clamp((p.months_since_last_delinquency / 24.0) * 10.0, 0, 10)
    return clamp(s, 0, 100)


def score_amounts_owed(p: CreditProfile) -> float:
    s = 100.0
    util = p.revolving_utilization
    if util <= 0.01:
        s -= 2.0
    elif util <= 0.09:
        s += 5.0
    elif util <= 0.29:
        pass
    elif util <= 0.49:
        s -= 10.0
    elif util <= 0.74:
        s -= 25.0
    else:
        s -= 45.0
    s -= clamp(p.installment_balance_ratio * 20.0, 0, 20)
    if p.total_accounts < 3:
        s -= 5.0
    elif p.total_accounts >= 15:
        s -= 3.0
    return clamp(s, 0, 100)


def score_length_history(p: CreditProfile) -> float:
    s = 0.0
    s += clamp((p.age_oldest_acct_years / 20.0) * 60.0, 0, 60)
    s += clamp((p.avg_age_years / 10.0) * 40.0, 0, 40)
    return clamp(s, 0, 100)


def score_new_credit(p: CreditProfile) -> float:
    s = 100.0
    if p.hard_inquiries_12m == 0:
        s += 3.0
    elif p.hard_inquiries_12m == 1:
        s -= 5.0
    elif p.hard_inquiries_12m == 2:
        s -= 10.0
    else:
        s -= 20.0
    if p.new_accounts_12m == 0:
        s += 2.0
    elif p.new_accounts_12m == 1:
        s -= 5.0
    elif p.new_accounts_12m == 2:
        s -= 10.0
    else:
        s -= 18.0
    return clamp(s, 0, 100)


def score_mix(p: CreditProfile) -> float:
    s = 50.0
    if p.has_revolving:
        s += 15.0
    if p.has_installment:
        s += 15.0
    if p.has_mortgage:
        s += 10.0
    if p.has_student_or_auto:
        s += 5.0
    return clamp(s, 0, 100)


WEIGHTS: Dict[str, float] = {
    "payment_history": 0.35,
    "amounts_owed": 0.30,
    "length_history": 0.15,
    "new_credit": 0.10,
    "credit_mix": 0.10,
}


def fico_like(p: CreditProfile) -> Tuple[float, Dict[str, float]]:
    ph = score_payment_history(p)
    ao = score_amounts_owed(p)
    lh = score_length_history(p)
    nc = score_new_credit(p)
    cm = score_mix(p)
    weighted_0_100 = (
        WEIGHTS["payment_history"] * ph
        + WEIGHTS["amounts_owed"] * ao
        + WEIGHTS["length_history"] * lh
        + WEIGHTS["new_credit"] * nc
        + WEIGHTS["credit_mix"] * cm
    )
    score_300_850 = round(300 + (weighted_0_100 / 100.0) * (850 - 300), 0)
    breakdown = {
        "payment_history": ph,
        "amounts_owed": ao,
        "length_history": lh,
        "new_credit": nc,
        "credit_mix": cm,
        "weighted_index_0_100": round(weighted_0_100, 2),
    }
    return score_300_850, breakdown


# ================== VALIDATION ==================
NUM_INT_FIELDS = [
    "late_30",
    "late_60",
    "late_90p",
    "months_since_last_delinquency",
    "total_accounts",
    "hard_inquiries_12m",
    "new_accounts_12m",
]
NUM_FLOAT_FIELDS = [
    "revolving_utilization",
    "installment_balance_ratio",
    "age_oldest_acct_years",
    "avg_age_years",
]
BOOL_FIELDS = [
    "has_collection",
    "has_bankruptcy",
    "has_mortgage",
    "has_installment",
    "has_revolving",
    "has_student_or_auto",
]


def parse_profile_partial(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    errors: Dict[str, str] = {}
    data: Dict[str, Any] = {}

    # ints
    for f in NUM_INT_FIELDS:
        if f in payload and payload[f] is not None:
            try:
                data[f] = int(payload[f])
            except (TypeError, ValueError):
                errors[f] = "must be integer"

    # floats
    for f in NUM_FLOAT_FIELDS:
        if f in payload and payload[f] is not None:
            try:
                data[f] = float(payload[f])
            except (TypeError, ValueError):
                errors[f] = "must be float"

    # bools
    for f in BOOL_FIELDS:
        if f in payload and payload[f] is not None:
            if isinstance(payload[f], bool):
                data[f] = payload[f]
            elif str(payload[f]).lower() in ["true", "false"]:
                data[f] = str(payload[f]).lower() == "true"
            else:
                errors[f] = "must be boolean"

    # range checks
    if "revolving_utilization" in data and not (0.0 <= data["revolving_utilization"] <= 1.0):
        errors["revolving_utilization"] = "range 0.0–1.0"
    if "installment_balance_ratio" in data and not (0.0 <= data["installment_balance_ratio"] <= 1.0):
        errors["installment_balance_ratio"] = "range 0.0–1.0"

    return data, errors


# ---- Dummy generator: deterministic per seed ----

def make_dummy_profile(seed: Optional[Union[str, int]] = None) -> CreditProfile:
    rng = random.Random()
    if seed is not None:
        # Convert seed to string to handle both str and int types
        str_seed = str(seed)
        h = int(hashlib.sha256(str_seed.encode("utf-8")).hexdigest(), 16) % (10**8)
        rng.seed(h)

    # Payment history
    late_30 = rng.choices([0, 1, 2], weights=[0.80, 0.15, 0.05])[0]
    late_60 = rng.choices([0, 1], weights=[0.92, 0.08])[0]
    late_90p = rng.choices([0, 1], weights=[0.97, 0.03])[0]
    has_collection = rng.random() < 0.06
    has_bankruptcy = rng.random() < 0.01
    months_since_last_delinquency: Optional[int] = None
    if (late_30 + late_60 + late_90p) > 0 or has_collection or has_bankruptcy:
        months_since_last_delinquency = rng.randint(0, 36)

    # Amounts owed / utilization
    if rng.random() < 0.7:
        revolving_utilization = round(rng.uniform(0.02, 0.29), 2)
    else:
        revolving_utilization = round(rng.uniform(0.30, 0.95), 2)
    installment_balance_ratio = round(rng.uniform(0.10, 0.90), 2)

    # Accounts & ages
    total_accounts = rng.randint(3, 18)
    age_oldest_acct_years = round(rng.uniform(2, 20), 1)
    avg_age_years = round(
        max(0.5, min(age_oldest_acct_years - rng.uniform(0.5, 6.0), age_oldest_acct_years)), 1
    )

    # New credit
    hard_inquiries_12m = rng.choices([0, 1, 2, 3, 4], weights=[0.55, 0.25, 0.12, 0.06, 0.02])[0]
    new_accounts_12m = rng.choices([0, 1, 2, 3], weights=[0.60, 0.25, 0.12, 0.03])[0]

    # Mix
    has_revolving = True
    has_installment = rng.random() < 0.75
    has_mortgage = rng.random() < 0.35
    has_student_or_auto = rng.random() < 0.30

    return CreditProfile(
        late_30=late_30,
        late_60=late_60,
        late_90p=late_90p,
        has_collection=has_collection,
        has_bankruptcy=has_bankruptcy,
        months_since_last_delinquency=months_since_last_delinquency,
        revolving_utilization=revolving_utilization,
        installment_balance_ratio=installment_balance_ratio,
        total_accounts=total_accounts,
        age_oldest_acct_years=age_oldest_acct_years,
        avg_age_years=avg_age_years,
        hard_inquiries_12m=hard_inquiries_12m,
        new_accounts_12m=new_accounts_12m,
        has_mortgage=has_mortgage,
        has_installment=has_installment,
        has_revolving=has_revolving,
        has_student_or_auto=has_student_or_auto,
    )
