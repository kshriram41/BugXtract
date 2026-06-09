from openpyxl import descriptors
from openpyxl.utils import indexed_list
from numpy._core.defchararray import title
from openpyxl.utils import indexed_list
from openpyxl.utils import indexed_list
from openpyxl.utils import indexed_list
from openpyxl.utils import indexed_list
import traceback
import os
import json
import logging
import datetime
import requests
import pandas as pd
from flask import Flask, render_template, request, jsonify, session, Response
from sentence_transformers import SentenceTransformer, util

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BugXtract")

app = Flask(__name__)
app.secret_key = 'bugxtract_ai_secret_key_for_development'
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads').replace('\\', '/')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper to check allowed extensions
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Load sentence-transformers model globally for duplicate detection
logger.info("Initializing SentenceTransformer model (all-MiniLM-L6-v2)...")
try:
    similarity_model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("SentenceTransformer model loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load SentenceTransformer model: {str(e)}")
    similarity_model = None

# Ollama Endpoint Configuration
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"

def get_metadata_json_path():
    return os.path.join(app.config['UPLOAD_FOLDER'], 'triage_metadata.json').replace('\\', '/')

def query_ollama_triage(title, description):
    """
    Sends the bug report to local Ollama running qwen2.5:3b to extract triage data.
    """
    prompt = f"""You are a software engineering bug triage AI agent.
1. Classify severity: Choose exactly one of "Low", "Medium", "High", "Critical".

SEVERITY DECISION RULES (MANDATORY)

Apply these rules BEFORE any other reasoning.

====================================================
CRITICAL
====================================================

IF the bug mentions:
- unauthorized access
- admin page access without authentication
- privilege escalation
- authentication bypass
- security vulnerability exposing sensitive data
- access control failure
- duplicate payment
- charged twice
- charged multiple times
- system outage
- complete data loss

Examples:
- User accesses admin dashboard without login
- User views another customer's account
- Payment processed twice
- Customer charged multiple times
- Authentication bypass vulnerability
- Entire application unavailable
- Database deleted or corrupted

THEN severity MUST be "Critical".

====================================================
HIGH
====================================================

IF the bug mentions:
- application crash
- service unavailable
- API returning 500 errors
- checkout process completely blocked
- file upload completely fails
- dashboard takes more than 30 seconds to load
- severe performance degradation
- core functionality completely broken with no workaround

Examples:
- Application crashes after login
- Checkout page crashes during payment
- Users cannot upload files
- Dashboard takes 45 seconds to load
- API returns Internal Server Error
- Core workflow completely blocked

THEN severity MUST be "High".

====================================================
MEDIUM
====================================================

IF the bug mentions:
- SQL exception
- database timeout
- PDF export corrupted
- export issue
- reporting issue
- password reset email not received
- user profile image not updating
- search functionality not working correctly
- notification email failure
- validation error
- feature partially working
- workaround exists
- report generation issue
- upload/download issue affecting only one feature

Examples:
- SQL Exception on Login
- Database timeout in a module
- PDF Export Corrupted
- Password Reset Email Not Received
- User Profile Image Not Updating
- Search results not loading correctly
- Notification emails not sent
- Reports generated incorrectly
- Feature works intermittently

THEN severity MUST be "Medium".

====================================================
LOW
====================================================

IF the bug mentions:
- cosmetic issue
- alignment issue
- typo
- spelling mistake
- color issue
- styling issue
- minor UI issue
- non-critical warning message

Examples:
- Button misaligned
- Wrong font size
- Typo in page title
- Incorrect icon color
- Spacing issue between fields
- Minor visual inconsistency

THEN severity MUST be "Low".

Do not choose a lower severity if a higher severity rule matches.

Examples:

BUG: Payment processed twice after checkout
Severity: Critical

BUG: Unauthorized access to admin page
Severity: Critical

BUG: Application crashes after login attempts
Severity: High

BUG: Dashboard takes 45 seconds to load
Severity: High

BUG: PDF export corrupted
Severity: Medium

BUG: Typo in footer links
Severity: Low

Analyze the following bug report:
Title: {title}
Description: {description}

Perform the following tasks:
1. Classify severity: Choose exactly one of "Low", "Medium", "High", "Critical".
   - You MUST classify as "Critical" if there is:
     * Unauthorized access to an admin page or restricted directory (e.g., accessing admin page controls without auth)
     * Duplicate payment processing or duplicate charging (e.g., charged twice)
     * System outage or complete data loss
   - You MUST classify as "High" if there is:
     * Application crash
     * Login failure
     * Performance issues above 30 seconds (e.g., taking 45 seconds to load)
   - You MUST classify as "Medium" if:
     * Feature partially working, workaround exists
   - You MUST classify as "Low" if:
     * Cosmetic, text mistakes, minor UI/styling issues

2. Classify area/component: Select exactly one of: Auth, Billing, Reporting, UI, API, Database, Security, Performance, General.
   Guidelines:
   - Login, password, authentication -> Auth
   - Payment, billing, invoice -> Billing
   - PDF, export, reports -> Reporting
   - Admin access, permissions, authorization, unauthorized access -> Security
   - Slow loading, timeout, latency -> Performance

3. Generate root cause prediction: Predict the most likely technical cause in one clear sentence.
4. Generate suggested fix: Generate a likely fix or resolution recommendation in 1-2 sentences. Keep it concise.
5. Auditing: Check if the bug report description contains:
   a) Steps to Reproduce
   b) Error Message
   c) Expected Behavior
6. Generate clarification message: If any of the above three items are missing, write a polite, professional message requesting the missing details. If none are missing, leave this empty.
7. Confidence Score: Estimate your analysis confidence level as an integer from 0 to 100.
8. Severity Reasoning: Explain in one brief sentence why the specific severity was assigned.

You must respond ONLY with a JSON object matching this schema (do not write any conversational text, markdown formatting, or explanation):
{{
  "severity": "Critical" (MUST be assigned for security bugs, unauthorized access, privilege escalation, and duplicate payments) | "High" (for crashes, login failures, performance over 30 seconds) | "Medium" | "Low",
  "area": "Auth" | "Billing" | "Reporting" | "UI" | "API" | "Database" | "Security" | "Performance" | "General",
  "root_cause_prediction": "One sentence prediction of the technical root cause.",
  "suggested_fix": "Concise 1-2 sentence recommendation on how to fix this issue.",
  "missing_steps_to_reproduce": true | false,
  "missing_error_message": true | false,
  "missing_expected_behavior": true | false,
  "clarification_message": "Polite clarification message if items are missing, otherwise empty string.",
  "confidence_score": 85,
  "severity_reasoning": "Reasoning explanation text for the assigned severity level."
}}
"""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "format": "json",
        "stream": False
    }
    
    try:
        print(f"\n[DEBUG] Sending request to Ollama. Timeout: 60s.")
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        print(f"[DEBUG] Ollama Response Status Code: {response.status_code}")
        print(f"[DEBUG] Ollama Response text: {response.text}")
        
        if response.status_code == 200:
            result_json = response.json()
            message_content = result_json.get('message', {}).get('content', '')
            print(f"[DEBUG] Extracted Message Content:\n{message_content}")
            
            # Sanitization and JSON extraction
            content_str = message_content.strip()
            
            # Find the outer JSON boundaries to handle model conversational prefix/postscript
            first_brace = content_str.find('{')
            last_brace = content_str.rfind('}')
            if first_brace != -1 and last_brace != -1:
                content_str = content_str[first_brace:last_brace+1]
                print(f"[DEBUG] Extracted JSON block:\n{content_str}")
            
            try:
                parsed_data = json.loads(content_str)
            except json.JSONDecodeError as jde:
                print(f"[ERROR] json.loads() failed to decode JSON content: {str(jde)}")
                import traceback
                traceback.print_exc()
                raise jde
                
            # Normalize confidence score
            if 'confidence_score' in parsed_data:
                try:
                    parsed_data['confidence_score'] = int(parsed_data['confidence_score'])
                except ValueError:
                    parsed_data['confidence_score'] = 80
            else:
                parsed_data['confidence_score'] = 80
                
            if 'severity_reasoning' not in parsed_data:
                parsed_data['severity_reasoning'] = f"Severity evaluated as {parsed_data.get('severity', 'Medium')} based on the technical impact described in the bug report."
            return parsed_data
        else:
            raise Exception(f"Ollama API returned status code {response.status_code}")
            
    except Exception as e:
        logger.exception("Error during query_ollama_triage")
        
        # Default triage values if Ollama is unresponsive or returns invalid JSON
        return {
            "severity": "Medium",
            "area": "General",
            "root_cause_prediction": "Unable to connect to Ollama to generate root cause prediction.",
            "suggested_fix": "Please check the Ollama service status.",
            "missing_steps_to_reproduce": False,
            "missing_error_message": False,
            "missing_expected_behavior": False,
            "clarification_message": "",
            "confidence_score": 0,
            "severity_reasoning": "Ollama service was unavailable to evaluate severity reasoning."
        }


def get_triaged_json_path():
    return os.path.join(app.config['UPLOAD_FOLDER'], 'triaged_bugs.json').replace('\\', '/')

def calculate_stats(results):
    total = len(results)
    duplicates = sum(1 for b in results if b.get('duplicate_status') != "Original")
    high_priority = sum(1 for b in results if b.get('severity', '').lower() in ['high', 'critical'])
    avg_health = round(sum(b.get('health_score', 100) for b in results) / total, 1) if total > 0 else 100.0
    
    # Load analysis time metrics
    total_time = "0.0s"
    last_run = "N/A"
    try:
        meta_path = get_metadata_json_path()
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                meta = json.load(f)
                total_time = meta.get('total_analysis_time', '0.0s')
                last_run = meta.get('last_analysis_run', 'N/A')
    except Exception:
        pass
        
    return {
        'total': total,
        'duplicates': duplicates,
        'high_priority': high_priority,
        'avg_health': f"{avg_health}%",
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
                    
            # Default mappings if not found
            id_col = col_mapping.get('id', df.columns[0])
            title_col = col_mapping.get('title', df.columns[1] if len(df.columns) > 1 else df.columns[0])
            desc_col = col_mapping.get('description', df.columns[2] if len(df.columns) > 2 else title_col)
            
            bugs = []
            for idx, row in df.iterrows():
                bugs.append({
                    'id': str(row.get(id_col, f'BUG-{100+idx}')),
                    'title': str(row.get(title_col, 'Untitled Bug')),
                    'description': str(row.get(desc_col, ''))
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
                
                # Query Ollama for every bug report
                ai_data = query_ollama_triage(title, desc)
                logger.info(f"Ollama response received for {bug_id}")
                print(f"Ollama response received for {bug_id}")
                
                severity = ai_data.get('severity', 'Medium')
                area = ai_data.get('area', 'General')
                root_cause = ai_data.get('root_cause_prediction', '')
                suggested_fix = ai_data.get('suggested_fix', 'Review code diagnostics.')
                confidence_score = ai_data.get('confidence_score', 80)
                severity_reasoning = ai_data.get('severity_reasoning', '')
                
                # Audit missing information
                missing_info_list = []
                if ai_data.get('missing_steps_to_reproduce', False):
                    missing_info_list.append("Steps to Reproduce")
                if ai_data.get('missing_error_message', False):
                    missing_info_list.append("Error Message")
                if ai_data.get('missing_expected_behavior', False):
                    missing_info_list.append("Expected Behavior")
                    
                clarification = ai_data.get('clarification_message', '')
                
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
                    'severity': severity,
                    'area': area,
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
                    'resolution_summary': ''
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
            
            # Save metadata
            try:
                with open(get_metadata_json_path(), 'w') as f:
                    json.dump({
                        'total_analysis_time': elapsed_str,
                        'last_analysis_run': last_run_timestamp
                    }, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to write metadata: {str(e)}")
                
            # Write results to triaged_bugs.json
            with open(get_triaged_json_path(), 'w') as f:
                json.dump(triaged_results, f, indent=2)
                
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
    json_path = get_triaged_json_path()
    if not os.path.exists(json_path):
        return jsonify({
            'success': False,
            'results': [],
            'stats': {
                'total': 0,
                'duplicates': 0,
                'high_priority': 0,
                'avg_health': '100.0%',
                'total_analysis_time': '0.0s',
                'last_analysis_run': 'N/A'
            }
        })
    try:
        with open(json_path, 'r') as f:
            results = json.load(f)
        stats = calculate_stats(results)
        return jsonify({
            'success': True,
            'results': results,
            'stats': stats
        })
    except Exception as e:
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
        
    json_path = get_triaged_json_path()
    if not os.path.exists(json_path):
        return jsonify({'error': 'No triage data found. Please run analysis first.'}), 400
        
    try:
        with open(json_path, 'r') as f:
            results = json.load(f)
            
        bug_found = False
        for bug in results:
            if bug['id'] == bug_id:
                bug_found = True
                bug['status'] = new_status
                if new_status == 'Fixed':
                    # Populate resolution info
                    now = datetime.datetime.now()
                    bug['date_fixed'] = now.strftime('%Y-%m-%d %H:%M')
                    bug['suggested_fix_applied'] = 'Yes'
                    bug['resolution_summary'] = 'Applied the suggested code patch to resolve the technical root cause.'
                else:
                    # Clear resolution info if status is rolled back
                    bug['date_fixed'] = ''
                    bug['suggested_fix_applied'] = ''
                    bug['resolution_summary'] = ''
                break
                
        if not bug_found:
            return jsonify({'error': f'Bug with ID {bug_id} not found.'}), 404
            
        # Save back to file
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2)
            
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
    json_path = get_triaged_json_path()
    if not os.path.exists(json_path):
        return "No triage data found. Please run analysis first.", 400
        
    try:
        with open(json_path, 'r') as f:
            results = json.load(f)
            
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
                'Area': bug.get('area'),
                'Duplicate Status': bug.get('duplicate_status'),
                'Health Score': bug.get('health_score'),
                'Missing Information': missing_info_str,
                'Clarification Message': bug.get('clarification_message'),
                'Root Cause Prediction': bug.get('root_cause_prediction'),
                'Suggested Fix': bug.get('suggested_fix'),
                'Confidence Score': f"{bug.get('confidence_score', 80)}%",
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
