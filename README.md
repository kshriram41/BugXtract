# BugXtract – AI Powered Bug Report Triage Agent

## Overview

BugXtract is an AI-powered bug triage system that automates the analysis and prioritization of software defect reports using a locally hosted Large Language Model (LLM).

The application helps QA engineers and development teams classify bugs, identify duplicates, estimate severity, predict root causes, and generate suggested fixes automatically.

---

## Features

### AI-Based Bug Triage

* Severity Classification (Low, Medium, High, Critical)
* Area Classification (Auth, Billing, UI, Reporting, Security, Performance, etc.)
* AI Severity Reasoning
* Root Cause Prediction
* Suggested Fix Generation
* Confidence Score Estimation

### Duplicate Detection

* Sentence Transformer Embeddings
* Cosine Similarity Matching
* Duplicate Candidate Identification
* Similarity Score Calculation

### Bug Quality Assessment

* Missing Information Detection
* Clarification Message Generation
* Health Score Calculation

### Dashboard Features

* CSV Upload
* Real-Time Analysis Progress
* Interactive Results Dashboard
* Status Tracking
* CSV Export

---

## Tech Stack

### Frontend

* HTML
* CSS
* JavaScript

### Backend

* Python
* Flask

### AI Models

* Ollama
* qwen2.5:3b

### NLP & Machine Learning

* sentence-transformers
* all-MiniLM-L6-v2
* scikit-learn

---

## Project Architecture

1. User uploads bug reports in CSV format.
2. Flask backend processes each bug.
3. Ollama (qwen2.5:3b) performs AI triage.
4. Sentence Transformers identify duplicate reports.
5. Results are displayed on the dashboard.
6. Users can export analyzed reports as CSV.

---

## Installation

### Clone Repository

```bash
git clone <repository-url>
cd BugXtract
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start Ollama

```bash
ollama serve
```

### Pull Model

```bash
ollama pull qwen2.5:3b
```

### Run Application

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

## Sample Dataset

The repository contains sample bug reports in:

```text
data/sample_bugs.csv
```

---

## Test Cases

The project has been validated for:

* Severity Classification
* Area Classification
* Duplicate Detection
* Missing Information Detection
* Confidence Score Generation
* Suggested Fix Generation
* CSV Export
* Status Tracking

---

## Future Enhancements

* Jira Integration
* Multi-Model Support
* Automated Bug Assignment
* Historical Bug Learning
* Cloud Deployment

---
