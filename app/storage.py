from pathlib import Path
import uuid

BASE_DIR = Path('data')
UPLOAD_DIR = BASE_DIR / 'uploads'
WORK_DIR = BASE_DIR / 'work'
RESULT_DIR = BASE_DIR / 'results'

for d in [UPLOAD_DIR, WORK_DIR, RESULT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def new_job_id() -> str:
    return uuid.uuid4().hex


def job_dirs(job_id: str):
    upload = UPLOAD_DIR / job_id
    work = WORK_DIR / job_id
    result = RESULT_DIR / job_id
    upload.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    result.mkdir(parents=True, exist_ok=True)
    return upload, work, result
