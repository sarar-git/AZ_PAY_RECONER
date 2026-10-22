# Amazon Payment Reconciliation System (Phase-2)

A production-oriented rewrite with:

- User signup/login
- Background job processing (non-blocking uploads)
- Chunked single-pass ingestion for large TSV files
- Stored job history + downloadable results
- Robust reserve boundary handling for sparse/mixed settlement files

## Highlights

1. **Authentication**
   - `/signup`, `/login`, `/logout`
   - user-scoped job history and file access

2. **Async processing flow**
   - Upload files -> returns `job_id`
   - Poll status via `/status/<job_id>`
   - Download final workbook from `/result/<job_id>`

3. **Memory-safe ingestion**
   - TSV read in chunks (`chunksize=100_000`)
   - Canonical transaction schema built once
   - Transform sheets from canonical data (no repeated file scans)

4. **Edge-case tolerance**
   - Files with only reserves
   - Files with only misc adjustments
   - Missing orders/refunds/ATS
   - Date-only reserve boundary logic with zero-respecting sums

## New structure

```
app/
  api.py        # Flask routes and auth/session flow
  jobs.py       # background worker execution
  ingest.py     # single-pass chunked normalization
  transforms.py # PAY/ORDERS/REFUNDS/OTHERS/BILL + Excel generation
  balance.py    # reserve boundary engine
  db.py         # sqlite users/jobs
  storage.py    # filesystem layout and job folders
```

## Run locally

```bash
pip install -r requirements.txt
python wsgi.py
```

Open: `http://localhost:5000`

## Data storage

All runtime state is persisted under `data/`:

- `data/app.db` (users/jobs)
- `data/uploads/<job_id>/`
- `data/work/<job_id>/`
- `data/results/<job_id>/Amazon_Reconciliation.xlsx`
