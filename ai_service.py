import os
import json
import logging
import requests
import config

logger = logging.getLogger("BugXtract.AIService")

REQUIRED_FIELDS = ["severity", "priority", "area", "recommended_team", "root_cause", "suggested_fix", "confidence"]

ALLOWED_AREAS = [
    "Authentication", "Billing", "Database", "Infrastructure", "Network", "Security",
    "DevOps", "Cloud", "API", "ERP Integration", "Monitoring", "Performance",
    "Data Pipeline", "Access Control", "Compliance", "Backend", "Frontend"
]

ALLOWED_TEAMS = [
    "Backend Team", "Frontend Team", "Database Team", "Infrastructure Team",
    "Network Team", "Security Team", "DevOps Team", "QA Team"
]

def get_triage_prompt(title, description, source_team, model_name):
    return f"""You are an expert software engineering bug triage AI agent specializing in enterprise software, cloud infrastructure, internal B2B business systems, ERP integrations, network operations, security incidents, and production environments.
Assume bug reports originate from corporate/internal teams: QA Teams, Testing Teams, IT Support Teams, Developers, DevOps Teams, Infrastructure Teams, Security Teams.
Do not optimize classifications for simple consumer or end-user issues.

Analyze the following bug report:
Title: {title}
Description: {description}
Source Team: {source_team}

Perform the following classifications:
1. Classify severity: Choose exactly one of "Low", "Medium", "High", "Critical".
   Apply these rules:
   - "Critical": Clean unauthorized access, SSO/auth system failures, direct privilege escalation, database replica outages, system outage, data corruption/loss, payment billing duplication (charged twice).
   - "High": Core service crash, replication delays (e.g. replica lag over 30 mins), gateway rate-limiting blocking partners, order sync failures between enterprise systems, monitoring platform alert failures.
   - "Medium": Partial features failing with workarounds, minor reporting discrepancies, validation errors.
   - "Low": Minor cosmetic bugs, UI layout misalignment, typos.

2. Classify priority: Choose exactly one of "P0", "P1", "P2", "P3".
   - P0 corresponds to Critical severity.
   - P1 corresponds to High severity.
   - P2 corresponds to Medium severity.
   - P3 corresponds to Low severity.

3. Classify area: Choose exactly one from the following allowed Area list:
   Authentication, Billing, Database, Infrastructure, Network, Security, DevOps, Cloud, API, ERP Integration, Monitoring, Performance, Data Pipeline, Access Control, Compliance, Backend, Frontend.

4. Recommend team: Choose exactly one from the following allowed Recommended Team list (do NOT return generic values such as "Developer", "Engineering", or "Technical Team"):
   Backend Team, Frontend Team, Database Team, Infrastructure Team, Network Team, Security Team, DevOps Team, QA Team.

5. Echo source_team: Use the exact string passed in as Source Team: "{source_team}".
6. Add model_used: Set this value to "{model_name}".

7. Generate root_cause: Predict the most likely technical cause in one clear sentence.
8. Generate suggested_fix: Recommend a fix or resolution in 1-2 concise sentences.
9. Confidence Score: Estimate your analysis confidence level as an integer from 0 to 100.

EXAMPLES FOR FEW-SHOT GUIDANCE:

Example 1:
Title: Corporate SSO Authentication Failure
Description: Employees across multiple business units are unable to authenticate through Azure Active Directory SSO after the latest identity provider configuration update.
Source Team: QA
Expected:
{{
  "severity": "Critical",
  "priority": "P0",
  "area": "Authentication",
  "source_team": "QA",
  "recommended_team": "Security Team",
  "root_cause": "SSO identity provider configuration mismatch or invalid signing certificate after the update.",
  "suggested_fix": "Roll back the identity provider configuration update and verify AAD metadata trust settings.",
  "confidence": 95,
  "model_used": "{model_name}"
}}

Example 2:
Title: Database Replication Lag
Description: The secondary PostgreSQL replica is experiencing a replication delay exceeding 45 minutes, causing outdated data to appear in reporting dashboards.
Source Team: Developer
Expected:
{{
  "severity": "High",
  "priority": "P1",
  "area": "Database",
  "source_team": "Developer",
  "recommended_team": "Database Team",
  "root_cause": "High write volumes on primary node or network throughput bottleneck between replica nodes.",
  "suggested_fix": "Increase replication buffer size, optimize queries, and inspect network metrics between primary and replica database instances.",
  "confidence": 90,
  "model_used": "{model_name}"
}}

Example 3:
Title: SAP Order Synchronization Failure
Description: Customer orders created in SAP are not being synchronized to the internal order management platform after the middleware upgrade.
Source Team: QA
Expected:
{{
  "severity": "High",
  "priority": "P1",
  "area": "ERP Integration",
  "source_team": "QA",
  "recommended_team": "Backend Team",
  "root_cause": "Incompatible schema translation or endpoint mismatch in SAP middleware synchronization protocol after upgrade.",
  "suggested_fix": "Validate API endpoints and verify message payload formatting against updated SAP middleware schema specifications.",
  "confidence": 90,
  "model_used": "{model_name}"
}}

Example 4:
Title: Kubernetes Worker Node Failure
Description: Two worker nodes in the production Kubernetes cluster entered NotReady state causing service degradation.
Source Team: DevOps Team
Expected:
{{
  "severity": "Critical",
  "priority": "P0",
  "area": "Infrastructure",
  "source_team": "DevOps Team",
  "recommended_team": "DevOps Team",
  "root_cause": "Worker node resource exhaustion (kubelet OOM) or underlying network connectivity failure in cloud provider.",
  "suggested_fix": "Evict pending pods, scale the cluster node group, and inspect kubelet logs on the affected worker nodes.",
  "confidence": 95,
  "model_used": "{model_name}"
}}

Example 5:
Title: Privilege Escalation Vulnerability
Description: Users assigned to the Finance Analyst role can access payroll administration screens through direct URL manipulation.
Source Team: Security Team
Expected:
{{
  "severity": "Critical",
  "priority": "P0",
  "area": "Security",
  "source_team": "Security Team",
  "recommended_team": "Security Team",
  "root_cause": "Lack of server-side role-based authorization check on payroll administration routing endpoint.",
  "suggested_fix": "Implement strict role verification checks on the payroll administration controller endpoints, avoiding reliance on hidden client URL controls.",
  "confidence": 95,
  "model_used": "{model_name}"
}}

Example 6:
Title: API Gateway Rate Limiting Misconfiguration
Description: The API gateway is rejecting legitimate partner requests due to incorrect rate limiting policies deployed during the latest release.
Source Team: QA
Expected:
{{
  "severity": "High",
  "priority": "P1",
  "area": "API",
  "source_team": "QA",
  "recommended_team": "Backend Team",
  "root_cause": "Incorrect rate limiting threshold values configured in the API gateway deployment manifest during release.",
  "suggested_fix": "Update gateway YAML rules to increase the threshold limit and hot-redeploy configuration policies.",
  "confidence": 90,
  "model_used": "{model_name}"
}}

Example 7:
Title: Production Monitoring Alert Failure
Description: Critical production application failures are occurring but no alerts are being generated by the monitoring platform.
Source Team: DevOps Team
Expected:
{{
  "severity": "High",
  "priority": "P1",
  "area": "Monitoring",
  "source_team": "DevOps Team",
  "recommended_team": "DevOps Team",
  "root_cause": "Alerting integration channel misconfiguration or alert rule criteria mismatch in monitoring tool.",
  "suggested_fix": "Test alerting channel endpoints manually and update alert criteria match patterns.",
  "confidence": 90,
  "model_used": "{model_name}"
}}

You must respond ONLY with a JSON object matching this schema (do not write any conversational text, markdown formatting, or explanation):
{{
  "severity": "Critical" | "High" | "Medium" | "Low",
  "priority": "P0" | "P1" | "P2" | "P3",
  "area": "Authentication" | "Billing" | "Database" | "Infrastructure" | "Network" | "Security" | "DevOps" | "Cloud" | "API" | "ERP Integration" | "Monitoring" | "Performance" | "Data Pipeline" | "Access Control" | "Compliance" | "Backend" | "Frontend",
  "source_team": "QA" | "Testing" | "IT Support" | "Developer" | "DevOps Team" | "Infrastructure Team" | "Security Team",
  "recommended_team": "Backend Team" | "Frontend Team" | "Database Team" | "Infrastructure Team" | "Network Team" | "Security Team" | "DevOps Team" | "QA Team",
  "root_cause": "One sentence prediction of the technical root cause.",
  "suggested_fix": "Concise 1-2 sentence recommendation on how to fix this issue.",
  "confidence": 85,
  "model_used": "{model_name}"
}}
"""

def validate_response(data, source_team_fallback, expected_model):
    if not isinstance(data, dict):
        return False
        
    # Enforce source_team to always match the exact CSV value (no LLM abbreviation like "QA")
    data["source_team"] = source_team_fallback
    if "model_used" not in data or not data["model_used"]:
        data["model_used"] = expected_model
        
    # Check all fields exist
    REQUIRED_FIELDS_V2 = ["severity", "priority", "area", "source_team", "recommended_team", "root_cause", "suggested_fix", "confidence", "model_used"]
    for field in REQUIRED_FIELDS_V2:
        if field not in data:
            return False
            
    # Validate types/values
    if data["severity"] not in ["Critical", "High", "Medium", "Low"]:
        return False
    if data["priority"] not in ["P0", "P1", "P2", "P3"]:
        return False
    if data["area"] not in ALLOWED_AREAS:
        return False
    if data["recommended_team"] not in ALLOWED_TEAMS:
        return False
    
    # Try parsing confidence as int
    try:
        data["confidence"] = int(data["confidence"])
        if not (0 <= data["confidence"] <= 100):
            return False
    except (ValueError, TypeError):
        return False
        
    return True

def get_fallback_defaults(source_team_fallback):
    return {
        "severity": "Unknown",
        "priority": "Unknown",
        "area": "Unknown",
        "source_team": source_team_fallback,
        "recommended_team": "Unknown",
        "root_cause": "AI services unavailable",
        "suggested_fix": "Check AI service connectivity",
        "confidence": 0,
        "model_used": "Unavailable",
        "router_status": "ALL_MODELS_FAILED",
        "classification_status": "AI_UNAVAILABLE"
    }

def analyze_bug_with_gemini(title, description, source_team):
    """
    Calls Gemini API to analyze the bug report.
    Raises an exception if it fails or if validation fails.
    """
    api_key = config.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in config.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = get_triage_prompt(title, description, source_team, "Gemini")
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    # Try twice (initial attempt + 1 retry)
    for attempt in range(2):
        try:
            logger.info(f"[ROUTER] Trying Gemini (Attempt {attempt + 1})...")
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            
            candidates = res_json.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates found in Gemini response.")
            
            content_parts = candidates[0].get("content", {}).get("parts", [])
            if not content_parts:
                raise ValueError("No content parts found in Gemini response.")
                
            text = content_parts[0].get("text", "")
            if not text:
                raise ValueError("Empty text part in Gemini response.")
                
            data = json.loads(text.strip())
            print(f"\n[RAW GEMINI OUTPUT]\n{text.strip()}\n")
            
            if validate_response(data, source_team, "Gemini"):
                data["model_used"] = "Gemini"
                data["router_status"] = "PRIMARY_SUCCESS"
                data["classification_status"] = "SUCCESS"
                logger.info("[ROUTER] Gemini Success")
                return data
            else:
                logger.warning(f"Gemini response failed validation: {text}")
                raise ValueError("Response failed schema/value validation.")
                
        except Exception as e:
            logger.warning(f"Error during Gemini call (Attempt {attempt + 1}): {str(e)}")
            if attempt == 0:
                logger.info("Retrying Gemini API call once...")
                import time
                time.sleep(1)
            else:
                raise e

def analyze_bug_with_groq(title, description, source_team):
    """
    Calls Groq API to analyze the bug report.
    Raises an exception if it fails or if validation fails.
    """
    api_key = config.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in config.")

    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = get_triage_prompt(title, description, source_team, "Groq")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    
    # Try twice (initial attempt + 1 retry)
    for attempt in range(2):
        try:
            logger.info(f"[ROUTER] Trying Groq (Attempt {attempt + 1})...")
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            res_json = response.json()
            
            choices = res_json.get("choices", [])
            if not choices:
                raise ValueError("No choices found in Groq response.")
                
            text = choices[0].get("message", {}).get("content", "")
            if not text:
                raise ValueError("Empty content in Groq response.")
                
            data = json.loads(text.strip())
            print(f"\n[RAW GROQ OUTPUT]\n{text.strip()}\n")
            
            if validate_response(data, source_team, "Groq"):
                data["model_used"] = "Groq"
                data["router_status"] = "FALLBACK_TRIGGERED"
                data["classification_status"] = "SUCCESS"
                logger.info("[ROUTER] Groq Success")
                return data
            else:
                logger.warning(f"Groq response failed validation: {text}")
                raise ValueError("Response failed schema/value validation.")
                
        except Exception as e:
            logger.warning(f"Error during Groq call (Attempt {attempt + 1}): {str(e)}")
            if attempt == 0:
                logger.info("Retrying Groq API call once...")
                import time
                time.sleep(1)
            else:
                raise e

def analyze_bug(title, description, source_team):
    """
    Attempts Gemini first, falls back to Groq if Gemini fails.
    If both fail, returns safe fallback defaults.
    """
    # 1. Try Gemini
    try:
        logger.info("[ROUTER] Trying Gemini")
        return analyze_bug_with_gemini(title, description, source_team)
    except Exception as e:
        logger.warning(f"[ROUTER] Gemini Failed: {str(e)}")
        logger.info("[ROUTER] Switching to Groq")
        
        # 2. Try Groq
        try:
            return analyze_bug_with_groq(title, description, source_team)
        except Exception as ge:
            logger.error(f"[ROUTER] Groq Failed: {str(ge)}")
            logger.error("[ROUTER] All AI providers unavailable")
            
            # 3. Final Fallback
            return get_fallback_defaults(source_team)

