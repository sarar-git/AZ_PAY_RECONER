import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from .db import init_db, create_job, get_job, get_user_jobs
from .storage import new_job_id, job_dirs
from .jobs import enqueue

ALLOWED_EXTENSIONS = {'txt', 'tsv'}
DEFAULT_USER_ID = 1


def create_app():
    app = Flask(__name__, template_folder='../templates')

    app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me-in-env')
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH_MB', '200')) * 1024 * 1024

    init_db()

    @app.route('/favicon.ico')
    def favicon():
        return ('', 204)

    @app.route('/')
    def home():
        return redirect(url_for('dashboard'))

    @app.route('/dashboard')
    def dashboard():
        jobs = get_user_jobs(DEFAULT_USER_ID)
        return render_template('index.html', jobs=jobs)

    @app.route('/upload', methods=['POST'])
    def upload():
        files = request.files.getlist('files[]')
        valid = [f for f in files if f and '.' in f.filename and f.filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS]
        if not valid:
            return jsonify({'error': 'No valid files'}), 400

        job_id = new_job_id()
        upload_dir, _, _ = job_dirs(job_id)
        saved_paths = []
        for f in valid:
            name = secure_filename(f.filename)
            path = upload_dir / name
            f.save(path)
            saved_paths.append(str(path))

        create_job(job_id, DEFAULT_USER_ID)
        enqueue(job_id, DEFAULT_USER_ID, saved_paths)
        return jsonify({'job_id': job_id})

    @app.route('/status/<job_id>')
    def status(job_id):
        job = get_job(job_id)
        if not job:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'id': job['id'], 'status': job['status'], 'message': job['message'], 'warnings': job['warnings']})

    @app.route('/result/<job_id>')
    def result(job_id):
        job = get_job(job_id)
        if not job or job['status'] != 'completed':
            return redirect(url_for('dashboard'))
        path = Path(job['result_path'])
        if not path.exists():
            flash('Result file missing.')
            return redirect(url_for('dashboard'))
        return send_file(path, as_attachment=True, download_name=f'Amazon_Reconciliation_{job_id[:8]}.xlsx')

    return app
