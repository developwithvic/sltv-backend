import subprocess
import sys

# === List of required packages with versions ===
packages = [
    "fastapi",
    "uvicorn[standard]",
    "sqlmodel",
    "alembic",
    "pydantic-settings",
    "python-multipart",
    "passlib[bcrypt]",
    "bcrypt==3.2.2",
    "python-jose[cryptography]",
    "selenium",
    "webdriver-manager",
    "requests",
    "mailjet-rest",
    "jinja2",
    "asyncpg",
    "aiosqlite",
    "slowapi",
    "email-validator"
]

def install(package):
    """Install a Python package using pip."""
    try:
        print(f"📦 Installing {package} ...")
        # Use sys.executable to ensure pip is from the correct virtual env
        # Using list for arguments is safer for subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ Successfully installed {package}\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}\n")

if __name__ == "__main__":
    print("--- Starting package installation ---")
    for pkg in packages:
        install(pkg)
    print("--- All packages processed ---")
