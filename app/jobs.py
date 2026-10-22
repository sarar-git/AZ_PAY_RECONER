from concurrent.futures import ThreadPoolExecutor
import os
import traceback
from .db import set_job_status
from .ingest import ingest_tsv_files
from .transforms import generate_excel
from .storage import job_dirs

executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv('JOB_WORKERS', '2'))))


def run_job(job_id: str, user_id: int, file_paths):
    set_job_status(job_id, 'processing', 'Ingestion started')
    try:
        tx, settlements, reserves, warnings = ingest_tsv_files(file_paths)
        set_job_status(job_id, 'processing', 'Generating workbook')
        excel = generate_excel(tx, settlements, reserves)

        _, _, result_dir = job_dirs(job_id)
        result_path = result_dir / 'Amazon_Reconciliation.xlsx'
        with open(result_path, 'wb') as f:
            f.write(excel.read())

        set_job_status(job_id, 'completed', 'Done', warnings='\n'.join(warnings), result_path=str(result_path.resolve()))
    except Exception as e:
        error_message = f"{type(e).__name__}: {e}"
        set_job_status(job_id, 'failed', error_message, warnings=traceback.format_exc())


def enqueue(job_id: str, user_id: int, file_paths):
    return executor.submit(run_job, job_id, user_id, file_paths)
