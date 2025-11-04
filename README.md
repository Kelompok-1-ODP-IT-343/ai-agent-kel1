# Credit Score API

A small Flask API to calculate a FICO-like credit score and store/fetch user credit profiles via SQLite using SQLAlchemy.

## Project structure

- `app.py` — Flask app: routes and request handling only
- `services/scoring.py` — Business/domain logic: dataclass, scoring, validation, dummy data
- `repositories/database.py` — Database layer: SQLAlchemy engine, session, ORM model, conversions
- `data/` — SQLite database lives here (`credit.db`)
- `requirements.txt` — Python dependencies

## How to run

1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies.
3. Set up environment variables (copy `.env.example` to `.env` and fill in your Gemini API key).
4. Start the API server.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

python app.py
```

The server runs at `http://localhost:9090`.

## API

### Credit Score Endpoints

- `POST /api/v1/credit-score`
  - Body examples:
    - `{ "user_id": "U123" }` → fetch (or create dummy) then score
    - `{ "user_id": "U123", <overrides> }` → upsert then score
    - `{ <full/partial profile w/o user_id> }` → score only (no DB)

- `GET /api/v1/credit-profile/<user_id>` → fetch stored profile
- `POST|PUT /api/v1/credit-profile` → upsert profile from body

### Recommendation System Endpoint

- `POST /api/v1/recommendation-system`
  - Evaluates KPR (mortgage) applications using ensemble decision-making
  - Body:
    ```json
    {
      "kprApplication": {
        "data": {
          "userInfo": { "userId": 15, ... },
          "propertyValue": 2100000000,
          "loanAmount": 1785000000,
          "monthlyInstallment": 16500000,
          ...
        }
      },
      "creditScore": { ... }  // Optional, will auto-calculate if not provided
    }
    ```
  - Returns APPROVE/REJECT decision with confidence, reasons, and summary
  - Uses 3 evaluators: Rules-based, Gate (hard limits), and LLM (Gemini AI)
  - Final decision by majority vote (2 out of 3)

### Health Check

- `GET /health` → health check

## Notes
- This is an educational FICO-like model. It is not the actual FICO formula.
- CORS is enabled for common local dev origins. Adjust in `app.py` as needed.
