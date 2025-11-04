# Sample Request for Recommendation System

## Endpoint
POST http://localhost:9090/api/v1/recommendation-system

## Headers
Content-Type: application/json

## Request Body Example

### Option 1: With KPR Application (auto-calculate credit score)
```json
{
  "kprApplication": {
    "success": true,
    "message": "KPR application detail retrieved successfully",
    "data": {
      "applicationId": 37,
      "applicationNumber": "APP20251028-013",
      "userId": null,
      "propertyId": null,
      "kprRateId": null,
      "propertyType": "RUKO",
      "propertyValue": 2100000000,
      "propertyAddress": "Komplek Niaga Timur Blok B-5, Bekasi",
      "propertyCertificateType": "HGB",
      "developerName": "PT Niaga Kencana",
      "loanAmount": 1785000000,
      "loanTermYears": 300,
      "interestRate": 0.071,
      "monthlyInstallment": 16500000,
      "downPayment": 315000000,
      "ltvRatio": 85,
      "purpose": "BUSINESS",
      "status": "SUBMITTED",
      "submittedAt": "2025-10-28T09:15:00",
      "userInfo": {
        "userId": 15,
        "username": "humio",
        "email": "humio@yopmail.com",
        "phone": "0867823992317",
        "fullName": "Septi Andrian",
        "nik": "3401234567890798",
        "npwp": "1234566667890978",
        "birthDate": "2002-05-05",
        "birthPlace": "Jakarta ",
        "gender": "FEMALE",
        "maritalStatus": "SINGLE",
        "address": "Margonda",
        "city": "Bali",
        "province": "Bali Barat",
        "postalCode": "11561",
        "occupation": "PNS",
        "companyName": "Kemenag",
        "companyAddress": null,
        "monthlyIncome": 10000000
      }
    }
  }
}
```

### Option 2: With Pre-computed Credit Score
```json
{
  "kprApplication": {
    "data": {
      "propertyValue": 2100000000,
      "loanAmount": 1785000000,
      "monthlyInstallment": 16500000,
      "userInfo": {
        "userId": 15,
        "monthlyIncome": 10000000
      }
    }
  },
  "creditScore": {
    "success": true,
    "user_id": "15",
    "score": 805.0,
    "breakdown": {
        "amounts_owed": 96.0,
        "credit_mix": 90.0,
        "length_history": 60.0,
        "new_credit": 100,
        "payment_history": 100,
        "weighted_index_0_100": 91.8
    },
    "input_used": {
        "age_oldest_acct_years": 12.0,
        "avg_age_years": 6.0,
        "hard_inquiries_12m": 0,
        "has_bankruptcy": false,
        "has_collection": false,
        "has_installment": true,
        "has_mortgage": true,
        "has_revolving": true,
        "has_student_or_auto": false,
        "installment_balance_ratio": 0.45,
        "late_30": 0,
        "late_60": 0,
        "late_90p": 0,
        "months_since_last_delinquency": null,
        "new_accounts_12m": 0,
        "revolving_utilization": 0.08,
        "total_accounts": 8
    },
    "weights": {
        "amounts_owed": 0.3,
        "credit_mix": 0.1,
        "length_history": 0.15,
        "new_credit": 0.1,
        "payment_history": 0.35
    }
  }
}
```

## Expected Response
```json
{
  "success": true,
  "recommendation": {
    "decision": "APPROVE",
    "confidence": 0.8,
    "reasons": [
      "Tidak ditemukan pelanggaran batas risiko yang bersifat keras.",
      "Indikator utama berada dalam kisaran kebijakan internal.",
      "Estimasi rasio cicilan terhadap penghasilan (DTI): **165%** (acuan internal 45%).",
      "Estimasi rasio pinjaman terhadap nilai properti (LTV): **85%** (acuan internal 90%).",
      "Perkiraan skor kredit edukatif: **805** (target minimal 700).",
      "Estimasi cicilan bulanan: **Rp16.500.000**; estimasi penghasilan bulanan: **Rp10.000.000**.",
      "Estimasi pinjaman: **Rp1.785.000.000**; estimasi nilai properti: **Rp2.100.000.000**."
    ],
    "key_factors": {
      "derived": {
        "dti": 1.65,
        "ltv": 0.85,
        "fico_score": 805.0
      }
    },
    "summary": "Berdasarkan evaluasi menyeluruh, pengajuan dapat disetujui..."
  },
  "credit_score_used": {
    "user_id": "15",
    "score": 805.0,
    "breakdown": {
      "payment_history": 100,
      "amounts_owed": 96.0,
      "length_history": 60.0,
      "new_credit": 100,
      "credit_mix": 90.0
    }
  },
  "model_used": "models/gemini-2.5-flash-lite-preview-06-17"
}
```

## cURL Example
```bash
curl -X POST http://localhost:9090/api/v1/recommendation-system \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```
