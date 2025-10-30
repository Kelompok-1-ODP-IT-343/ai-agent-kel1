from dataclasses import asdict, replace
from typing import Dict, Any
from flask import Flask, request, jsonify
from flask_cors import CORS  # ← NEW

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
                "https://local-dev.satuatap.my.id", # your dev domain
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
    supports_credentials=False,  # set True only if you use cookies/session auth
)

## All business logic and DB code are located in services/ and repositories/

# ================== API ENDPOINTS ==================
@app.route("/api/v1/credit-score", methods=["POST"])
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

@app.route("/api/v1/credit-profile/<user_id>", methods=["GET"])
def get_credit_profile(user_id: str):
    with SessionLocal() as s:
        rec = s.get(CreditProfileORM, user_id)
        if not rec:
            return jsonify({"success": False, "message": "user_id tidak ditemukan"}), 404
        return jsonify({"success": True, "user_id": user_id, "profile": asdict(orm_to_dc(rec))})

@app.route("/api/v1/credit-profile", methods=["POST", "PUT"])
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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    # Dev server
    app.run(host="0.0.0.0", port=9090, debug=True)
