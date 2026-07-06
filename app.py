from openpyxl import descriptors
from openpyxl.utils import indexed_list
from numpy._core.defchararray import title
import traceback
import os
import json
import logging
import datetime
import requests
import pandas as pd
from flask import Flask, render_template, request, jsonify, session, Response
from sentence_transformers import SentenceTransformer, util
from database import init_db, get_db_connection
from ai_service import analyze_bug

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BugXtract")

app = Flask(__name__)
app.secret_key = 'bugxtract_ai_secret_key_for_development'
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads').replace('\\', '/')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder and database exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()

# Helper to check allowed extensions
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def row_to_bug_dict(row):
    bug = dict(row)
    # Map database column names to frontend dictionary keys
    bug['id'] = bug.pop('bug_id')
    bug['confidence_score'] = bug.pop('confidence')
    bug['root_cause_prediction'] = bug.pop('root_cause')
    if bug.get('missing_information'):
        bug['missing_information'] = [x.strip() for x in bug['missing_information'].split(',') if x.strip()]
    else:
        bug['missing_information'] = []
    return bug

# Load sentence-transformers model globally for duplicate detection
logger.info("Initializing SentenceTransformer model (all-MiniLM-L6-v2)...")
try:
    similarity_model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("SentenceTransformer model loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load SentenceTransformer model: {str(e)}")
    similarity_model = None

def audit_description(description):
    desc_lower = description.lower()
    # Programmatically determine if description has these fields
    missing_steps = not any(kw in desc_lower for kw in ["step", "reproduce", "repro", "how to"])
    missing_error = not any(kw in desc_lower for kw in ["error", "exception", "fail", "message", "crash", "bug", "traceback"])
    missing_expected = not any(kw in desc_lower for kw in ["expected", "should", "instead", "actual", "desired"])
    
    missing_fields = []
    if missing_steps:
        missing_fields.append("Steps to Reproduce")
    if missing_error:
        missing_fields.append("Error Message")
    if missing_expected:
        missing_fields.append("Expected Behavior")
        
    if missing_fields:
        clarification = "Hello, thank you for submitting this report. To help us triage this faster, could you please provide the missing details: " + ", ".join(missing_fields) + "?"
    else:
        clarification = ""
        
    return missing_fields, clarification


def calculate_stats(results):
    total = len(results)
    critical = sum(1 for b in results if b.get('severity', '').lower() == 'critical')
    high_priority = sum(1 for b in results if b.get('severity', '').lower() == 'high' or b.get('priority', '').lower() == 'p1')
    duplicates = sum(1 for b in results if b.get('duplicate_status') != "Original")
    open_bugs = sum(1 for b in results if b.get('status', '').lower() == 'open')
    resolved_bugs = sum(1 for b in results if b.get('status', '').lower() == 'fixed')
    
    # Load analysis time metrics from SQLite database
    total_time = "0.0s"
    last_run = "N/A"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'total_analysis_time'")
        row = cursor.fetchone()
        if row:
            total_time = row[0]
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_analysis_run'")
        row = cursor.fetchone()
        if row:
            last_run = row[0]
        conn.close()
    except Exception as e:
        logger.error(f"Failed to read metadata stats: {str(e)}")
        
    return {
        'total': total,
        'critical': critical,
        'high_priority': high_priority,
        'duplicates': duplicates,
        'open': open_bugs,
        'resolved': resolved_bugs,
        'total_analysis_time': total_time,
        'last_analysis_run': last_run
    }


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected for uploading'}), 400
    
    if file and allowed_file(file.filename):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'uploaded_bugs.csv').replace('\\', '/')
        file.save(file_path)
        
        try:
            df = pd.read_csv(file_path)
            row_count = len(df)
            columns = list(df.columns)
            
            # Map columns case-insensitively
            col_mapping = {}
            for col in df.columns:
                col_cleaned = col.strip().lower()
                if col_cleaned in ['bug id', 'bug_id', 'id']:
                    col_mapping['id'] = col
                elif col_cleaned in ['title', 'summary', 'name']:
                    col_mapping['title'] = col
                elif col_cleaned in ['description', 'desc', 'body', 'details']:
                    col_mapping['description'] = col
                elif col_cleaned in ['source team', 'source_team', 'sourceteam']:
                    col_mapping['source_team'] = col

            required = ['id', 'title', 'description', 'source_team']
            missing_headers = [r.replace('_', ' ').title() for r in required if r not in col_mapping]
            if missing_headers:
                return jsonify({'error': f'Validation Error: CSV is missing required column(s): {", ".join(missing_headers)}'}), 400

            # Validate missing values for Source Team in each row
            source_col = col_mapping['source_team']
            for idx, row in df.iterrows():
                val = str(row.get(source_col, '')).strip()
                if not val or val == 'nan':
                    return jsonify({'error': f'Validation Error: Row {idx + 1} has a missing value for "Source Team"'}), 400
            
            # Save file path and name to session
            session['uploaded_file_path'] = file_path
            session['uploaded_file_name'] = file.filename
            
            return jsonify({
                'success': True,
                'filename': file.filename,
                'rows': row_count,
                'columns': columns
            })
        except Exception as e:
            return jsonify({'error': f'Failed to parse CSV file: {str(e)}'}), 400
            
    return jsonify({'error': 'Invalid file type. Only CSV files are allowed.'}), 400

@app.route('/analyze', methods=['POST'])
def analyze_bugs():
    file_path = session.get('uploaded_file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'No uploaded file found. Please upload a CSV first.'}), 400
        
    def generate_events():
        import time
        start_time = time.time()
        
        try:
            df = pd.read_csv(file_path)
            
            # Standardize columns mapping (case-insensitive and whitespace flexible)
            col_mapping = {}
            for col in df.columns:
                col_cleaned = col.strip().lower()
                if col_cleaned in ['bug id', 'bug_id', 'id']:
                    col_mapping['id'] = col
                elif col_cleaned in ['title', 'summary', 'name']:
                    col_mapping['title'] = col
                elif col_cleaned in ['description', 'desc', 'body', 'details']:
                    col_mapping['description'] = col
                elif col_cleaned in ['source team', 'source_team', 'sourceteam']:
                    col_mapping['source_team'] = col
                    
            # Check mappings
            id_col = col_mapping.get('id')
            title_col = col_mapping.get('title')
            desc_col = col_mapping.get('description')
            source_col = col_mapping.get('source_team')
            
            if not id_col or not title_col or not desc_col or not source_col:
                raise ValueError("CSV is missing required column(s). Required: Bug ID, Title, Description, Source Team")
            
            bugs = []
            for idx, row in df.iterrows():
                bugs.append({
                    'id': str(row.get(id_col, f'BUG-{100+idx}')),
                    'title': str(row.get(title_col, 'Untitled Bug')),
                    'description': str(row.get(desc_col, '')),
                    'source_team': str(row.get(source_col, 'QA')).strip()
                })
                
            total_bugs = len(bugs)
            yield f"data: {json.dumps({'type': 'start', 'total': total_bugs})}\n\n"
            
            # 1. Duplicate Detection using sentence-transformers
            duplicate_statuses = []
            duplicate_candidates = []
            similarity_scores = []
            descriptions = [b['description'] for b in bugs]
            
            if similarity_model and len(descriptions) > 0:
                try:
                    embeddings = similarity_model.encode(descriptions, convert_to_tensor=True)
                    for i in range(len(bugs)):
                        max_sim = 0.0
                        best_match = None
                        for j in range(i):
                            sim = util.cos_sim(embeddings[i], embeddings[j]).item()
                            if sim > max_sim:
                                max_sim = sim
                                best_match = bugs[j]['id']
                                
                        sim_pct = int(round(max_sim * 100)) if i > 0 else 0
                        
                        if max_sim > 0.75 and best_match is not None:
                            duplicate_statuses.append(f"Duplicate of {best_match}")
                            duplicate_candidates.append(best_match)
                            similarity_scores.append(sim_pct)
                        else:
                            duplicate_statuses.append("Original")
                            duplicate_candidates.append(None)
                            similarity_scores.append(sim_pct)
                except Exception as e:
                    logger.error(f"Error computing duplicate detection: {str(e)}")
                    duplicate_statuses = ["Original"] * len(bugs)
                    duplicate_candidates = [None] * len(bugs)
                    similarity_scores = [0] * len(bugs)
            else:
                duplicate_statuses = ["Original"] * len(bugs)
                duplicate_candidates = [None] * len(bugs)
                similarity_scores = [0] * len(bugs)
                
            # 2. AI Triage, Completeness Auditing, and Scoring
            triaged_results = []
            
            for idx, bug in enumerate(bugs):
                bug_id = bug['id']
                title = bug['title']
                desc = bug['description']
                
                # Yield progress event before starting query
                yield f"data: {json.dumps({'type': 'progress', 'index': idx + 1, 'total': total_bugs, 'bug_id': bug_id, 'title': title})}\n\n"
                
                logger.info(f"Starting analysis of {bug_id}")
                print(f"Starting analysis of {bug_id}")
                
                dup_status = duplicate_statuses[idx]
                is_duplicate = dup_status != "Original"
                
                row_source_team = bug['source_team']
                allowed_source_teams = [
                    "QA Team", "Testing Team", "IT Support Team", "Developer Team",
                    "DevOps Team", "Security Team", "Infrastructure Team",
                    "Data Engineering Team", "Compliance Team"
                ]
                
                if row_source_team not in allowed_source_teams:
                    logger.warning(f"Invalid Source Team detected for {bug_id}: {row_source_team}")
                    severity = "Unknown"
                    priority = "Unknown"
                    area = "Unknown"
                    recommended_team = "Unknown"
                    root_cause = f"Invalid Source Team value: '{row_source_team}'"
                    suggested_fix = "Please correct the Source Team value in the CSV report and re-upload. Allowed teams: QA Team, Testing Team, IT Support Team, Developer Team, DevOps Team, Security Team, Infrastructure Team, Data Engineering Team, Compliance Team."
                    confidence_score = 0
                    model_used = "Unavailable"
                    router_status = "ALL_MODELS_FAILED"
                    classification_status = "INVALID_SOURCE_TEAM"
                else:
                    # Query AI Router for every bug report
                    ai_data = analyze_bug(title, desc, row_source_team)
                    logger.info(f"AI Router response received for {bug_id}")
                    print(f"AI Router response received for {bug_id}")
                    
                    row_source_team = ai_data.get('source_team', row_source_team)
                    severity = ai_data.get('severity', 'Medium')
                    priority = ai_data.get('priority', 'P2')
                    area = ai_data.get('area', 'General')
                    recommended_team = ai_data.get('recommended_team', 'Developer')
                    root_cause = ai_data.get('root_cause', '')
                    suggested_fix = ai_data.get('suggested_fix', 'Review code diagnostics.')
                    confidence_score = ai_data.get('confidence', 80)
                    model_used = ai_data.get('model_used', 'Gemini')
                    router_status = ai_data.get('router_status', 'PRIMARY_SUCCESS')
                    classification_status = ai_data.get('classification_status', 'SUCCESS')
                
                # Audit missing information programmatically
                missing_info_list, clarification = audit_description(desc)
                severity_reasoning = f"Severity evaluated as {severity} by {model_used} agent based on system impact."
                
                # Calculate Health Score
                health_score = 100
                if is_duplicate:
                    health_score -= 20
                health_score -= 10 * len(missing_info_list)
                if severity.lower() == 'critical':
                    health_score -= 20
                health_score = max(0, min(100, health_score))
 
                # If this bug is a duplicate, inherit severity from original bug
                if dup_status != "Original":
                    for existing_bug in triaged_results:
                        if existing_bug["id"] == duplicate_candidates[idx]:
                            severity = existing_bug["severity"]
                            break
 
                triaged_bug = {
                    'id': bug_id,
                    'title': title,
                    'description': desc,
                    'source_team': row_source_team,
                    'severity': severity,
                    'priority': priority,
                    'area': area,
                    'recommended_team': recommended_team,
                    'duplicate_status': dup_status,
                    'duplicate_candidate': duplicate_candidates[idx],
                    'similarity_score': similarity_scores[idx],
                    'health_score': health_score,
                    'missing_information': missing_info_list,
                    'clarification_message': clarification,
                    'root_cause_prediction': root_cause,
                    'suggested_fix': suggested_fix,
                    'confidence_score': confidence_score,
                    'severity_reasoning': severity_reasoning,
                    'status': 'Open',
                    'date_fixed': '',
                    'suggested_fix_applied': '',
                    'resolution_summary': '',
                    'model_used': model_used,
                    'router_status': router_status,
                    'classification_status': classification_status
                }


                triaged_results.append(triaged_bug)
                # Yield intermediate result
                yield f"data: {json.dumps({'type': 'bug_result', 'bug': triaged_bug, 'index': idx + 1, 'total': total_bugs})}\n\n"
                
                logger.info(f"Finished analysis of {bug_id}")
                print(f"Finished analysis of {bug_id}")
                
            # Measure elapsed time
            elapsed = round(time.time() - start_time, 2)
            elapsed_str = f"{elapsed:.1f}s"
            logger.info(f"Total analysis duration: {elapsed_str}")
            print(f"Total analysis duration: {elapsed_str}")
            last_run_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Save metadata to SQLite
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_analysis_time', ?)", (elapsed_str,))
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_analysis_run', ?)", (last_run_timestamp,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Failed to write metadata to SQLite: {str(e)}")
                
            # Write results to SQLite database
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM bugs")
                for b in triaged_results:
                    missing_info_str = ",".join(b.get('missing_information', []))
                    cursor.execute("""
                        INSERT OR REPLACE INTO bugs (
                            bug_id, title, description, source_team, severity, priority, area,
                            recommended_team, root_cause, suggested_fix, confidence, duplicate_status,
                            similarity_score, duplicate_candidate, health_score, missing_information,
                            clarification_message, severity_reasoning, status, date_fixed,
                            suggested_fix_applied, resolution_summary, model_used, router_status, classification_status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        b.get('id'),
                        b.get('title'),
                        b.get('description'),
                        b.get('source_team', ''),
                        b.get('severity'),
                        b.get('priority', ''),
                        b.get('area'),
                        b.get('recommended_team', ''),
                        b.get('root_cause_prediction'),
                        b.get('suggested_fix'),
                        b.get('confidence_score', 80),
                        b.get('duplicate_status'),
                        b.get('similarity_score', 0),
                        b.get('duplicate_candidate'),
                        b.get('health_score', 100),
                        missing_info_str,
                        b.get('clarification_message', ''),
                        b.get('severity_reasoning', ''),
                        b.get('status', 'Open'),
                        b.get('date_fixed', ''),
                        b.get('suggested_fix_applied', ''),
                        b.get('resolution_summary', ''),
                        b.get('model_used', 'Gemini'),
                        b.get('router_status', ''),
                        b.get('classification_status', '')
                    ))
                conn.commit()
                conn.close()
            except Exception as dbe:
                logger.error(f"Failed to write results to SQLite: {str(dbe)}")
                
            # Compile Stats
            stats = calculate_stats(triaged_results)
            
            yield f"data: {json.dumps({'type': 'complete', 'results': triaged_results, 'stats': stats})}\n\n"
            
        except Exception as e:
            traceback.print_exc()
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
    return Response(generate_events(), mimetype='text/event-stream')

@app.route('/triage_data', methods=['GET'])
def get_triage_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bugs ORDER BY rowid")
        rows = cursor.fetchall()
        conn.close()
        
        results = [row_to_bug_dict(row) for row in rows]
        stats = calculate_stats(results)
        return jsonify({
            'success': True,
            'results': results,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Failed to fetch triage data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_status', methods=['POST'])
def update_status():
    """
    Updates the status of a specific bug and captures resolution data if marked Fixed.
    """
    req_data = request.get_json() or {}
    bug_id = req_data.get('id')
    new_status = req_data.get('status')
    
    if not bug_id or not new_status:
        return jsonify({'error': 'Missing bug ID or status parameter'}), 400
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if bug exists
        cursor.execute("SELECT bug_id FROM bugs WHERE bug_id = ?", (bug_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': f'Bug with ID {bug_id} not found.'}), 404
            
        if new_status == 'Fixed':
            now = datetime.datetime.now()
            date_fixed = now.strftime('%Y-%m-%d %H:%M')
            fix_applied = 'Yes'
            res_summary = 'Applied the suggested code patch to resolve the technical root cause.'
        else:
            date_fixed = ''
            fix_applied = ''
            res_summary = ''
            
        cursor.execute("""
            UPDATE bugs
            SET status = ?, date_fixed = ?, suggested_fix_applied = ?, resolution_summary = ?
            WHERE bug_id = ?
        """, (new_status, date_fixed, fix_applied, res_summary, bug_id))
        conn.commit()
        
        # Fetch updated results
        cursor.execute("SELECT * FROM bugs ORDER BY rowid")
        rows = cursor.fetchall()
        results = [row_to_bug_dict(row) for row in rows]
        conn.close()
        
        # Recalculate Stats
        stats = calculate_stats(results)
        
        return jsonify({
            'success': True,
            'results': results,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Failed to update status: {str(e)}")
        return jsonify({'error': f'Failed to update bug status: {str(e)}'}), 500

@app.route('/export', methods=['GET'])
def export_results():
    """
    Exports the triaged bugs list to a CSV download.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bugs ORDER BY rowid")
        rows = cursor.fetchall()
        conn.close()
        
        results = [row_to_bug_dict(row) for row in rows]
        
        if not results:
            return "No triage data found. Please run analysis first.", 400
            
        # Build CSV file manually or with Pandas
        export_data = []
        for bug in results:
            # Join missing information list to a comma-separated string
            missing_info_str = ", ".join(bug.get('missing_information', []))
            
            export_data.append({
                'Bug ID': bug.get('id'),
                'Title': bug.get('title'),
                'Description': bug.get('description'),
                'Severity': bug.get('severity'),
                'Priority': bug.get('priority'),
                'Area': bug.get('area'),
                'Source Team': bug.get('source_team'),
                'Recommended Team': bug.get('recommended_team'),
                'Root Cause': bug.get('root_cause_prediction'),
                'Suggested Fix': bug.get('suggested_fix'),
                'Confidence': f"{bug.get('confidence_score', 80)}%",
                'Model Used': bug.get('model_used'),
                'Router Status': bug.get('router_status'),
                'Duplicate Status': bug.get('duplicate_status'),
                'Health Score': bug.get('health_score'),
                'Missing Information': missing_info_str,
                'Clarification Message': bug.get('clarification_message'),
                'AI Reasoning': bug.get('severity_reasoning', ''),
                'Status': bug.get('status'),
                'Date Fixed': bug.get('date_fixed'),
                'Resolution Summary': bug.get('resolution_summary')
            })
            
        df_export = pd.DataFrame(export_data)
        csv_content = df_export.to_csv(index=False)
        
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=bugxtract_triage_results.csv"}
        )
        
    except Exception as e:
        logger.error(f"Failed to export CSV: {str(e)}")
        return f"Failed to export CSV: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
