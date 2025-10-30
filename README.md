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
3. Start the API server.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The server runs at `http://localhost:9090`.

## API

- `POST /api/v1/credit-score`
  - Body examples:
    - `{ "user_id": "U123" }` → fetch (or create dummy) then score
    - `{ "user_id": "U123", <overrides> }` → upsert then score
    - `{ <full/partial profile w/o user_id> }` → score only (no DB)

- `GET /api/v1/credit-profile/<user_id>` → fetch stored profile
- `POST|PUT /api/v1/credit-profile` → upsert profile from body
- `GET /health` → health check

## Notes
- This is an educational FICO-like model. It is not the actual FICO formula.
- CORS is enabled for common local dev origins. Adjust in `app.py` as needed.
