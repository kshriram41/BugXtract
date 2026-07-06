import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger("BugXtract.Config")

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Validate Gemini API Key
if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in ("", "YOUR_GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE", "your_gemini_api_key_here"):
    raise RuntimeError(
        "\n======================================================================\n"
        "CRITICAL ERROR: GEMINI_API_KEY is missing!\n"
        "Please create a '.env' file in the project root containing:\n"
        "GEMINI_API_KEY=your_gemini_api_key_here\n"
        "======================================================================\n"
    )

# Validate Groq API Key
if not GROQ_API_KEY or GROQ_API_KEY.strip() in ("", "YOUR_GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE", "your_groq_api_key_here"):
    logger.warning("Groq fallback unavailable.")

