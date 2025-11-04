"""
Recommendation service for credit application approval.

This module provides ensemble decision-making using:
1. Rules-based evaluation (DTI, LTV, credit score thresholds)
2. Gate evaluation (hard limits for severe violations)
3. LLM evaluation (Gemini AI for narrative reasoning)

Final decision is determined by majority vote (2 out of 3).
"""

from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List
from collections import Counter

from dotenv import load_dotenv, find_dotenv
from google import genai

# Load environment variables
load_dotenv(find_dotenv(), override=True)


def _clean_env(val: Optional[str]) -> Optional[str]:
    """Clean environment variable values from quotes."""
    if val is None:
        return None
    v = val.strip()
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
        v = v[1:-1]
    return v.strip()


# Configuration from environment
API_KEY = _clean_env(os.getenv("GEMINI_API_KEY")) or _clean_env(os.getenv("GOOGLE_API_KEY"))
DEFAULT_MODEL = _clean_env(os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-lite-preview-06-17"))
FALLBACK_MODELS_ENV = _clean_env(os.getenv("FALLBACK_MODELS", ""))

DEFAULT_TEMPERATURE = float(_clean_env(os.getenv("TEMPERATURE", "0.3")) or 0.3)
DEFAULT_MAX_TOKENS = int(_clean_env(os.getenv("MAX_OUTPUT_TOKENS", "512")) or 512)

DEFAULT_MIN_SCORE = float(_clean_env(os.getenv("MIN_SCORE", "700")) or 700)
DEFAULT_MAX_DTI = float(_clean_env(os.getenv("MAX_DTI", "0.45")) or 0.45)
DEFAULT_MAX_LTV = float(_clean_env(os.getenv("MAX_LTV", "0.9")) or 0.9)


@dataclass
class Derived:
    """Derived metrics from application data."""
    dti: Optional[float]  # Debt-to-Income ratio
    ltv: Optional[float]  # Loan-to-Value ratio
    score: Optional[float]  # Credit score


@dataclass
class RuleConfig:
    """Configuration for rule-based evaluation."""
    min_score: float = DEFAULT_MIN_SCORE
    max_dti: float = DEFAULT_MAX_DTI
    max_ltv: float = DEFAULT_MAX_LTV


def derive_metrics(profile: Dict[str, Any], fico: Dict[str, Any]) -> Derived:
    """
    Extract and calculate key metrics from application profile and FICO score.
    
    Args:
        profile: KPR application profile containing user info and loan details
        fico: FICO credit score response
        
    Returns:
        Derived object with DTI, LTV, and score values
    """
    data = profile.get("data", {}) if isinstance(profile, dict) else {}
    u = data.get("userInfo", {}) if isinstance(data, dict) else {}
    
    income = u.get("monthlyIncome")
    installment = data.get("monthlyInstallment")
    loan = data.get("loanAmount")
    prop_val = data.get("propertyValue")
    score = fico.get("score")

    # Calculate DTI (Debt-to-Income)
    dti = None
    if installment and income and float(income) > 0:
        try:
            dti = float(installment) / float(income)
        except Exception:
            dti = None

    # Calculate LTV (Loan-to-Value)
    ltv = None
    if loan and prop_val and float(prop_val) > 0:
        try:
            ltv = float(loan) / float(prop_val)
        except Exception:
            ltv = None

    # Extract score
    try:
        score = float(score) if score is not None else None
    except Exception:
        score = None
        
    return Derived(dti=dti, ltv=ltv, score=score)


def pct(x: Optional[float]) -> str:
    """Format percentage."""
    return f"{x*100:.0f}%" if (x is not None) else "—"


def fmt_money(x: Optional[float]) -> str:
    """Format money in Indonesian rupiah."""
    if x is None:
        return "—"
    try:
        return f"Rp{x:,.0f}".replace(",", ".")
    except Exception:
        return str(x)


def human_summary(decision: str) -> str:
    """Generate human-readable summary based on decision."""
    if decision == "APPROVE":
        return ("Berdasarkan evaluasi menyeluruh, pengajuan **dapat disetujui**. "
                "Profil risiko berada dalam rentang yang dinilai wajar untuk produk sejenis.")
    return ("Untuk saat ini pengajuan **belum dapat kami setujui**. "
            "Pertimbangan ini diambil agar komitmen cicilan tetap sejalan dengan kemampuan bayar yang berkelanjutan.")


def human_bullets_for_metrics(profile: Dict[str, Any], fico: Dict[str, Any], d: Derived,
                              max_dti: float, max_ltv: float, min_score: float) -> List[str]:
    """Generate bullet points explaining key metrics."""
    data = profile.get("data", {}) if isinstance(profile, dict) else {}
    u = data.get("userInfo", {}) if isinstance(data, dict) else {}
    inc = u.get("monthlyIncome")
    inst = data.get("monthlyInstallment")
    loan = data.get("loanAmount")
    pv = data.get("propertyValue")

    return [
        f"Estimasi rasio cicilan terhadap penghasilan (DTI): **{pct(d.dti)}** (acuan internal {int(max_dti*100)}%).",
        f"Estimasi rasio pinjaman terhadap nilai properti (LTV): **{pct(d.ltv)}** (acuan internal {int(max_ltv*100)}%).",
        f"Perkiraan skor kredit edukatif: **{int(d.score) if d.score is not None else '—'}** (target minimal {int(min_score)}).",
        f"Estimasi cicilan bulanan: **{fmt_money(inst)}**; estimasi penghasilan bulanan: **{fmt_money(inc)}**.",
        f"Estimasi pinjaman: **{fmt_money(loan)}**; estimasi nilai properti: **{fmt_money(pv)}**."
    ]


def human_reasons(decision: str, rules_reason: List[str], gate_reason: List[str], llm_reason: List[str]) -> List[str]:
    """Combine reasons from all evaluators into concise human-readable list."""
    def pick(xs: List[str]) -> List[str]:
        out = []
        for x in xs or []:
            if x and x not in out:
                out.append(x)
            if len(out) >= 2:
                break
        return out

    reasons = pick(gate_reason) + pick(rules_reason) + pick(llm_reason)
    if not reasons:
        if decision == "APPROVE":
            reasons = ["Parameter risiko utama dinilai memadai untuk kategori produk ini."]
        else:
            reasons = ["Beberapa indikator risiko berada di atas batas kebijakan internal."]
    return reasons[:6]


def build_summary_paragraph(decision: str, d: Derived,
                            max_dti: float, max_ltv: float, min_score: float,
                            llm_notes: str = "") -> str:
    """Build complete summary paragraph with tips and disclaimer."""
    base = human_summary(decision)
    
    if decision == "REJECT":
        tips = []
        if d.dti is not None and d.dti > max_dti:
            tips.append("menurunkan rasio cicilan terhadap penghasilan (misalnya dengan menaikkan uang muka atau menyesuaikan tenor)")
        if d.ltv is not None and d.ltv > max_ltv:
            tips.append(f"menurunkan rasio pinjaman terhadap nilai properti (LTV) hingga ≤{int(max_ltv*100)}%")
        if d.score is not None and d.score < min_score:
            tips.append("menjaga riwayat pembayaran tetap baik dan mengurangi pengajuan kredit baru untuk sementara waktu")
        if tips:
            base += " Sebagai masukan, pertimbangkan " + "; ".join(tips) + "."

    note = (llm_notes or "").strip()
    if note:
        note = re.sub(r"\s+", " ", note)
        if len(note) > 350:
            note = note[:347] + "..."
        base += " " + note

    base += " Catatan: angka cicilan bulanan bersifat estimasi dan dapat berubah mengikuti ketentuan produk dan pergerakan suku bunga mengambang (floating)."
    return base


def rules_decide(profile: Dict[str, Any], fico: Dict[str, Any], cfg: RuleConfig) -> Dict[str, Any]:
    """
    Rules-based evaluation using DTI, LTV, and credit score thresholds.
    
    Returns decision dict with APPROVE/REJECT and reasons.
    """
    d = derive_metrics(profile, fico)
    approve = True
    reasons: List[str] = []

    if d.score is not None and d.score < cfg.min_score:
        approve = False
        reasons.append(f"Skor kredit sekitar {int(d.score)} berada di bawah kisaran acuan {int(cfg.min_score)}.")
        
    if d.dti is not None and d.dti > cfg.max_dti:
        approve = False
        reasons.append(f"Rasio cicilan terhadap penghasilan (DTI) {pct(d.dti)} melebihi batas {int(cfg.max_dti*100)}%.")
        
    if d.ltv is not None and d.ltv > cfg.max_ltv:
        approve = False
        reasons.append(f"Rasio pinjaman terhadap nilai properti (LTV) {pct(d.ltv)} melebihi batas {int(cfg.max_ltv*100)}%.")

    decision = "APPROVE" if approve else "REJECT"
    confidence = 0.75 if approve else 0.8
    
    return {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons if reasons else ["Indikator utama berada dalam kisaran kebijakan internal."],
        "key_factors": {"fico_score": d.score, "dti": d.dti, "ltv": d.ltv, "red_flags": []},
        "_derived": {"dti": d.dti, "ltv": d.ltv, "score": d.score},
    }


def gate_decide(profile: Dict[str, Any], fico: Dict[str, Any], cfg: RuleConfig) -> Dict[str, Any]:
    """
    Gate evaluation for hard limits (severe violations).
    
    Returns decision dict with APPROVE/REJECT and reasons.
    """
    d = derive_metrics(profile, fico)
    reasons: List[str] = []
    hard_fail = False

    if d.dti is not None and d.dti > (cfg.max_dti + 0.10):
        hard_fail = True
        reasons.append(f"DTI {pct(d.dti)} cukup jauh di atas batas {int(cfg.max_dti*100)}%.")
        
    if d.ltv is not None and d.ltv > (cfg.max_ltv + 0.05):
        hard_fail = True
        reasons.append(f"LTV {pct(d.ltv)} melampaui batas {int(cfg.max_ltv*100)}% dengan margin yang signifikan.")
        
    if d.score is not None and d.score < (cfg.min_score - 50):
        hard_fail = True
        reasons.append(f"Skor {int(d.score)} berada jauh di bawah kisaran yang diharapkan.")

    if hard_fail:
        decision, confidence = "REJECT", 0.9
    else:
        decision, confidence = "APPROVE", 0.7
        if not reasons:
            reasons = ["Tidak ditemukan pelanggaran batas risiko yang bersifat keras."]
            
    return {
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
        "key_factors": {"fico_score": d.score, "dti": d.dti, "ltv": d.ltv, "red_flags": []},
        "_derived": {"dti": d.dti, "ltv": d.ltv, "score": d.score},
    }


def extract_text(resp) -> str:
    """Extract text from Gemini API response."""
    if resp is None:
        return ""
    t = getattr(resp, "text", None)
    if t:
        return t
    cands = getattr(resp, "candidates", None)
    if not cands:
        return ""
    texts: List[str] = []
    for c in cands:
        content = getattr(c, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            for p in parts:
                pt = getattr(p, "text", None)
                if pt:
                    texts.append(pt)
    return "\n".join(texts).strip()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from text (handles code blocks and raw JSON)."""
    if not text:
        return None
    for pat in (r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```"):
        blocks = re.findall(pat, text, flags=re.DOTALL)
        for b in blocks:
            try:
                return json.loads(b)
            except Exception:
                pass
    fb, lb = text.find("{"), text.rfind("}")
    if fb != -1 and lb != -1 and lb > fb:
        frag = text[fb:lb+1]
        try:
            return json.loads(frag)
        except Exception:
            pass
    return None


def build_llm_prompt(profile: Dict[str, Any], fico: Dict[str, Any], d: Derived) -> str:
    """Build prompt for LLM evaluation."""
    schema = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["APPROVE", "REJECT"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "key_factors": {"type": "object", "additionalProperties": True},
            "conditions": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"}
        },
        "required": ["decision", "confidence", "reasons"]
    }
    guidance = """
Gunakan bahasa Indonesia yang komunikatif dan diplomatis. Keputusan hanya "APPROVE" atau "REJECT".
Jika menyebut angka (DTI/LTV/skor), jelaskan maknanya secara ringkas.
"""
    return f"""
Anda adalah underwriter senior KPR.
Evaluasi pengajuan berikut dari 2 JSON di bawah ini.
Keluarkan **HANYA** JSON sesuai skema (tanpa teks lain):
{json.dumps(schema, ensure_ascii=False)}

Nilai bantu:
- dti={d.dti if d.dti is not None else "null"}
- ltv={d.ltv if d.ltv is not None else "null"}
- fico_score={d.score if d.score is not None else "null"}

{guidance}

[PROFILE_JSON]
{json.dumps(profile, ensure_ascii=False)}

[FICO_JSON]
{json.dumps(fico, ensure_ascii=False)}
""".strip()


def call_gemini(prompt: str, model: str, temperature: float, max_tokens: int) -> Tuple[Optional[Dict[str, Any]], Optional[str], str]:
    """Call Gemini API with retry logic."""
    if not API_KEY:
        return None, "GEMINI_API_KEY not configured", ""
        
    client = genai.Client(api_key=API_KEY)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
            },
        )
        raw = extract_text(resp)
        parsed = extract_json(raw)
        if parsed:
            dec = (parsed.get("decision") or "").upper()
            if dec not in ("APPROVE", "REJECT"):
                parsed["decision"] = "REJECT"
            return parsed, None, raw
        return None, "LLM returned empty/non-JSON output", raw
    except Exception as e:
        return None, str(e), ""


def _norm_dec(x: Optional[str]) -> str:
    """Normalize decision to APPROVE or REJECT."""
    return "APPROVE" if (x or "").upper() == "APPROVE" else "REJECT"


def majority_vote(ballots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Determine final decision by majority vote (2 out of 3)."""
    decs = [_norm_dec(b.get("decision")) for b in ballots]
    cnt = Counter(decs)
    final = "APPROVE" if cnt["APPROVE"] >= 2 else "REJECT"
    return {"final": final, "tally": {"APPROVE": cnt["APPROVE"], "REJECT": cnt["REJECT"]}}


def decide_ensemble(
    profile: Dict[str, Any],
    fico: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS
) -> Dict[str, Any]:
    """
    Main ensemble decision function combining rules, gate, and LLM evaluations.
    
    Args:
        profile: KPR application profile JSON
        fico: FICO credit score response JSON
        model: Gemini model to use
        temperature: LLM temperature
        max_tokens: Max output tokens for LLM
        
    Returns:
        Decision dict with final decision, confidence, reasons, and summary
    """
    cfg = RuleConfig(
        min_score=DEFAULT_MIN_SCORE,
        max_dti=DEFAULT_MAX_DTI,
        max_ltv=DEFAULT_MAX_LTV
    )
    d = derive_metrics(profile, fico)

    # 1) Rules-based evaluation
    rules_res = rules_decide(profile, fico, cfg)
    rules_ballot = {
        "source": "rules",
        "decision": rules_res["decision"],
        "confidence": rules_res["confidence"],
        "reasons": rules_res["reasons"]
    }

    # 2) Gate evaluation
    gate_res = gate_decide(profile, fico, cfg)
    gate_ballot = {
        "source": "gate",
        "decision": gate_res["decision"],
        "confidence": gate_res["confidence"],
        "reasons": gate_res["reasons"]
    }

    # 3) LLM evaluation with fallback
    prompt = build_llm_prompt(profile, fico, d)
    fallbacks = [m.strip() for m in (FALLBACK_MODELS_ENV or "").split(",") if m.strip()]
    
    llm_ok, raw_text = None, None
    for m in [model] + fallbacks:
        parsed, err, raw = call_gemini(prompt, m, temperature, max_tokens)
        if parsed:
            llm_ok = {"model": m, "parsed": parsed}
            raw_text = raw
            break
        raw_text = raw

    if llm_ok:
        llm_decision = _norm_dec(llm_ok["parsed"].get("decision"))
        llm_conf = float(llm_ok["parsed"].get("confidence", 0.7) or 0.7)
        llm_reasons = llm_ok["parsed"].get("reasons", [])
        llm_notes = llm_ok["parsed"].get("notes", "")
        llm_ballot = {
            "source": "llm",
            "decision": llm_decision,
            "confidence": llm_conf,
            "reasons": llm_reasons
        }
        llm_model_used = llm_ok["model"]
        llm_hint_factors = llm_ok["parsed"].get("key_factors", {})
    else:
        llm_ballot = {
            "source": "llm",
            "decision": "REJECT",
            "confidence": 0.6,
            "reasons": ["Saat ini sistem AI tidak memberikan respons yang dapat diandalkan, sehingga kami mengambil pendekatan konservatif."]
        }
        llm_model_used = None
        llm_hint_factors = {}
        llm_notes = "—"

    # 4) Majority voting
    ballots = [rules_ballot, gate_ballot, llm_ballot]
    vote = majority_vote(ballots)
    final_decision = vote["final"]

    # 5) Build human-readable output
    reasons = human_reasons(
        final_decision,
        rules_ballot["reasons"],
        gate_ballot["reasons"],
        llm_ballot["reasons"]
    )
    reasons += human_bullets_for_metrics(profile, fico, d, cfg.max_dti, cfg.max_ltv, cfg.min_score)

    summary = build_summary_paragraph(
        final_decision, d,
        cfg.max_dti, cfg.max_ltv, cfg.min_score,
        llm_notes=llm_notes
    )

    # Confidence: 0.9 for unanimous (3-0), 0.8 for majority (2-1)
    conf = 0.9 if vote["tally"][final_decision] == 3 else 0.8

    result = {
        "decision": final_decision,
        "confidence": conf,
        "reasons": reasons[:10],
        "key_factors": {
            "derived": {"dti": d.dti, "ltv": d.ltv, "fico_score": d.score},
            "rules": rules_res.get("key_factors", {}),
            "gate": gate_res.get("key_factors", {}),
            "llm_hint": llm_hint_factors,
        },
        "summary": summary,
    }
    
    return {
        "source": "ensemble",
        "result": result,
        "model": llm_model_used,
        "raw": raw_text
    }
