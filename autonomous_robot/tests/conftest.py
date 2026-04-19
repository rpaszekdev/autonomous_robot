import os
import sys
from pathlib import Path

# Make the `robot` package importable without installing.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Stub env so config.load() never runs during handler tests that happen to import it.
os.environ.setdefault("GOOGLE_API_KEY", "test-not-a-real-key")
os.environ.setdefault("GEMINI_MODEL", "gemini-test")
