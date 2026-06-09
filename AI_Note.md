**AI Note – BugXtract**

**Introduction**

_BugXtract is an AI-powered bug triage system developed to simplify the process of analyzing and prioritizing software bug reports. In software projects, manually reviewing large numbers of bug reports can be time-consuming and inconsistent. This project addresses that challenge by using Artificial Intelligence to automate key bug triage tasks._



The system accepts bug reports through a CSV file and provides intelligent insights such as severity classification, duplicate detection, root cause prediction, and suggested fixes.



**AI Technologies Used**

The project uses the qwen2.5:3b Large Language Model running locally through Ollama. This allows bug reports to be analyzed without relying on external cloud services.



**The AI model is responsible for:**



Understanding bug descriptions



Classifying bug severity



Identifying the affected component



Predicting possible root causes



Generating suggested fixes



Providing reasoning for its decisions



Estimating confidence scores



In addition to the language model, semantic similarity techniques are used to identify duplicate bug reports.



How the AI Works

When a CSV file is uploaded, each bug report is processed individually. The title and description are sent to the AI model, which analyzes the information and generates structured outputs.



**The system automatically determines:**



Severity Level (Low, Medium, High, Critical)



Affected Area or Component



Root Cause Prediction



Suggested Fix



Confidence Score


AI Reasoning



Duplicate detection is performed by comparing bug descriptions using semantic similarity, helping teams avoid handling the same issue multiple times.



**Benefits of Using AI**

Integrating AI into bug triage provides several advantages:



Reduces manual effort during bug analysis



Speeds up issue prioritization



Improves consistency in bug classification



Helps developers understand possible causes quickly



Supports better decision-making during software maintenance



**Limitations**

Although AI can provide useful recommendations, its output depends on the quality of the bug descriptions provided. Poorly documented reports may lead to lower confidence predictions. Therefore, AI-generated results should be considered as assistance rather than final decisions.



**Conclusion**

BugXtract demonstrates how Artificial Intelligence can be applied to software quality assurance processes. By combining Large Language Models and semantic similarity techniques, the system helps automate bug triage and improves the efficiency of managing software defects.

