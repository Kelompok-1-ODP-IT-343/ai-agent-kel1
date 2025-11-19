from dataclasses import asdict, replace
from typing import Dict, Any, Callable, Iterable
import os
import functools
from flask import Flask, request, jsonify
from flask_cors import CORS  # ← NEW
import jwt

# ---- Import domain services & repositories ----
from services.scoring import (
    CreditProfile,
    fico_like,
    WEIGHTS,
    parse_profile_partial,
    make_dummy_profile,
)
from repositories.database import (
    SessionLocal,
    CreditProfileORM,
    orm_to_dc,
    dc_to_orm,
)

# ================== APP & DB SETUP ==================
app = Flask(__name__)
app.url_map.strict_slashes = False

# Enable CORS for API routes (adjust origins for your env)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",            # Next.js dev
                "http://127.0.0.1:3000",
                "http://localhost:8080",            # if you ever proxy FE here
                "http://127.0.0.1:8080",
                "http://localhost:3002",
                "http://127.0.0.1:3002",       
                "http://localhost:3004",
                "http://127.0.0.1:3004", 
                "http://localhost:3001",
                "http://127.0.0.1:3001",     # if you ever proxy FE here
                "http://localhost:3003",
                "http://127.0.0.1:3003",
                "https://admin.satuatap.my.id", # your dev domain
                "https://staff.satuatap.my.id",
                "https://developer.satuatap.my.id"
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
    supports_credentials=False,  # set True only if you use cookies/session auth
)

## All business logic and DB code are located in services/ and repositories/

# ================== AUTH (JWT) ==================
ALLOWED_ROLES = {"APPROVER", "DEVELOPER", "ADMIN"}
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS384")


def _decode_jwt_from_header() -> Dict[str, Any]:
    """Decode JWT from Authorization: Bearer <token> header.
    - Returns the decoded claims dict if successf   ul.
    - Raises ValueError with message on client errors (missing/format/invalid token).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise ValueError("Authorization header missing")
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("Authorization header must be 'Bearer <token>'")
    token = parts[1]

    # Prefer verifying signature when secret is configured; otherwise decode without verification (development only).
    try:
        if JWT_SECRET:
            claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        else:
            # No secret configured — decode without signature verification (NOT recommended for production)
            claims = jwt.decode(
                token,
                options={"verify_signature": True, "verify_exp": True},
                algorithms=[JWT_ALGORITHM],
            )
        return claims
    except jwt.exceptions.InvalidTokenError as e:
        # Covers expired, invalid signature, decode errors, etc.
        raise ValueError(f"Invalid token: {str(e)}")


def require_roles(roles: Iterable[str]) -> Callable:
    """Flask route decorator that enforces role-based access via JWT.

    - Accepts a collection of allowed role names.
    - 401 if token missing/invalid; 403 if role not permitted.
    """

    allowed = {r.upper() for r in roles}

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                claims = _decode_jwt_from_header()
            except ValueError as e:
                return jsonify({"success": False, "message": str(e)}), 401

            role = str(claims.get("role", "")).upper()
            if role not in allowed:
                return (
                    jsonify({
                        "success": False,
                        "message": "forbidden: role not permitted",
                        "role": role or None,
                        "allowed_roles": sorted(list(allowed)),
                    }),
                    403,
                )
            # Optionally expose claims to downstream handlers via request context if needed
            request.jwt_claims = claims  # type: ignore[attr-defined]
            return fn(*args, **kwargs)

        return wrapper

    return decorator

# ================== API ENDPOINTS ==================
@app.route("/api/v2/credit-score", methods=["POST"])
@require_roles(ALLOWED_ROLES)
def credit_score():
    """
    Body:
    - {"user_id":"U123"} → fetch from DB (or create dummy), then score
    - {"user_id":"U123", <overrides>} → upsert then score
    - {<full/partial profile w/o user_id>} → score only (no DB)
    """
    if not request.is_json:
        return jsonify({"success": False, "message": "Content-Type harus application/json"}), 400

    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    # Normalize user_id to string if present (handles int PKs from JSON)
    if user_id is not None:
        user_id = str(user_id)

    overrides, errors = parse_profile_partial(payload)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    from_db = False
    created = False
    persisted = False

    if user_id:
        with SessionLocal() as s:
            rec = s.get(CreditProfileORM, user_id)
            if rec is None:
                dc = make_dummy_profile(seed=user_id)
                if overrides:
                    dc = replace(dc, **overrides)
                rec = dc_to_orm(user_id, dc)
                s.add(rec)
                s.commit()
                created = True
                from_db = True
                persisted = True
            else:
                dc = orm_to_dc(rec)
                if overrides:
                    dc = replace(dc, **overrides)
                    rec = dc_to_orm(user_id, dc, obj=rec)
                    s.add(rec)
                    s.commit()
                    persisted = True
                from_db = True

        with SessionLocal() as s:
            final_rec = s.get(CreditProfileORM, user_id)
            profile_dc = orm_to_dc(final_rec)
    else:
        base = make_dummy_profile()
        profile_dc = replace(base, **overrides) if overrides else base

    score, breakdown = fico_like(profile_dc)
    return jsonify({
        "success": True,
        "source": {"from_db": from_db, "created_if_missing": created, "persisted_changes": persisted},
        "user_id": user_id,
        "input_used": asdict(profile_dc),
        "weights": WEIGHTS,
        "score": score,
        "breakdown": breakdown,
        "note": "Model edukatif FICO-like (BUKAN rumus FICO asli)."
    })

@app.route("/api/v2/credit-profile/<user_id>", methods=["GET"])
@require_roles(ALLOWED_ROLES)
def get_credit_profile(user_id: str):
    with SessionLocal() as s:
        rec = s.get(CreditProfileORM, user_id)
        if not rec:
            return jsonify({"success": False, "message": "user_id tidak ditemukan"}), 404
        return jsonify({"success": True, "user_id": user_id, "profile": asdict(orm_to_dc(rec))})

@app.route("/api/v2/credit-profile", methods=["POST", "PUT"])
@require_roles(ALLOWED_ROLES)
def upsert_credit_profile():
    if not request.is_json:
        return jsonify({"success": False, "message": "Content-Type harus application/json"}), 400
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "user_id wajib"}), 400
    # Normalize user_id to string (handles int PKs from JSON)
    user_id = str(user_id)

    overrides, errors = parse_profile_partial(payload)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    with SessionLocal() as s:
        rec = s.get(CreditProfileORM, user_id)
        if rec is None:
            base = make_dummy_profile(seed=user_id)
            dc = replace(base, **overrides) if overrides else base
            rec = dc_to_orm(user_id, dc)
            s.add(rec)
            s.commit()
            return jsonify({"success": True, "created": True, "user_id": user_id, "profile": asdict(dc)})
        else:
            dc = orm_to_dc(rec)
            dc = replace(dc, **overrides)
            rec = dc_to_orm(user_id, dc, obj=rec)
            s.add(rec)
            s.commit()
            return jsonify({"success": True, "created": False, "user_id": user_id, "profile": asdict(dc)})

@app.route("/api/v2/recommendation-system", methods=["POST"])
@require_roles(ALLOWED_ROLES)
def recommendation_system():
    """
    KPR Recommendation System endpoint.
    
    Body:
    - {
        "kprApplication": {...},  // KPR application data with userInfo
        "creditScore": {...}      // Optional: pre-computed FICO score
      }
    
    If creditScore is not provided, it will be calculated using userId from kprApplication.
    """
    if not request.is_json:
        return jsonify({"success": False, "message": "Content-Type harus application/json"}), 400

    payload = request.get_json(silent=True) or {}
    kpr_application = payload.get("kprApplication")
    credit_score_data = payload.get("creditScore")

    if not kpr_application:
        return jsonify({"success": False, "message": "kprApplication wajib"}), 400

    # Extract user_id from kprApplication
    try:
        data = kpr_application.get("data", {}) if isinstance(kpr_application, dict) else {}
        user_info = data.get("userInfo", {}) if isinstance(data, dict) else {}
        user_id = user_info.get("userId")
        
        if not user_id:
            return jsonify({"success": False, "message": "userId tidak ditemukan dalam kprApplication"}), 400
        
        # Normalize user_id to string
        user_id = str(user_id)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error parsing kprApplication: {str(e)}"}), 400

    # Get or compute credit score
    if credit_score_data:
        # Use provided credit score
        fico_response = credit_score_data
    else:
        # Compute credit score from our system
        with SessionLocal() as s:
            rec = s.get(CreditProfileORM, user_id)
            if rec is None:
                # Create dummy profile if not exists
                dc = make_dummy_profile(seed=user_id)
                rec = dc_to_orm(user_id, dc)
                s.add(rec)
                s.commit()
            profile_dc = orm_to_dc(rec)

        score, breakdown = fico_like(profile_dc)
        fico_response = {
            "success": True,
            "source": {"from_db": True},
            "user_id": user_id,
            "input_used": asdict(profile_dc),
            "weights": WEIGHTS,
            "score": score,
            "breakdown": breakdown,
        }

    # Run recommendation system
    try:
        from services.recommendation_service import decide_ensemble
        
        result = decide_ensemble(
            profile=kpr_application,
            fico=fico_response
        )
        
        return jsonify({
            "success": True,
            "recommendation": result["result"],
            "credit_score_used": {
                "user_id": user_id,
                "score": fico_response.get("score"),
                "breakdown": fico_response.get("breakdown", {})
            },
            "model_used": result.get("model"),
            "timestamp": data.get("timestamp") if isinstance(data, dict) else None
        })
        
    except ImportError:
        return jsonify({
            "success": False,
            "message": "Recommendation service not available. Please install required dependencies: google-genai, python-dotenv"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error processing recommendation: {str(e)}"
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    # Dev server
    app.run(host="0.0.0.0", port=9009, debug=True)
