"""Stage 0 gate checks (no API calls). Run from the repo root: python tests/test_setup.py"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_packages_import():
    import dotenv, gradio, openai, pypdf  # noqa: F401


def test_skeleton_exists():
    for p in ["me", "logs", "tests", "react_agent.ipynb", ".env.example", ".gitignore", "README.md",
              "requirements.txt", "me/about_business.pdf", "me/business_summary.txt"]:
        assert (ROOT / p).exists(), f"missing {p}"


def test_env_is_git_ignored():
    for p in [".env", ".venv/", "logs/leads.jsonl", ".gradio/"]:
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode == 0, f"{p} is NOT ignored by git"


def test_env_example_has_no_real_key():
    text = (ROOT / ".env.example").read_text()
    assert "GEMINI_API_KEY=your-key-here" in text
    assert "AIza" not in text


def test_key_loads():
    from dotenv import dotenv_values
    key = dotenv_values(ROOT / ".env").get("GEMINI_API_KEY") or ""
    assert key, "GEMINI_API_KEY is empty in .env"
    assert key == key.strip() and not key.startswith(('"', "'")), "remove quotes/spaces around the key"
    print("  key:", key[:4] + "...")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    raise SystemExit(failed)
