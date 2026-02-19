#!/usr/bin/env python
"""
AI Trading Agent Setup Verification

Run this script to verify the agent is configured correctly.

Usage:
    python agent_setup.py
"""
import sys
import os

def check_dependencies():
    """Check required dependencies"""
    print("Checking dependencies...")

    required = [
        ('python-dotenv', 'dotenv'),
        ('httpx', 'httpx'),
        ('anthropic', 'anthropic'),
        ('alpaca-py', 'alpaca'),
        ('rich', 'rich'),
        ('websockets', 'websockets'),
        ('yfinance', 'yfinance'),
    ]

    missing = []
    for package_name, import_name in required:
        try:
            __import__(import_name)
            print(f"  ✓ {package_name}")
        except ImportError:
            print(f"  ✗ {package_name} - NOT INSTALLED")
            missing.append(package_name)

    return missing


def check_environment():
    """Check environment variables"""
    print("\nChecking environment variables...")

    from dotenv import load_dotenv
    load_dotenv()

    vars_to_check = [
        ('ALPACA_API_KEY', True),
        ('ALPACA_SECRET_KEY', True),
        ('ANTHROPIC_API_KEY', True),
        ('ALPACA_BASE_URL', False),  # Optional, has default
    ]

    missing = []
    for var_name, required in vars_to_check:
        value = os.getenv(var_name)
        if value:
            # Mask the value for security
            masked = value[:4] + '****' + value[-4:] if len(value) > 8 else '****'
            print(f"  ✓ {var_name}: {masked}")
        elif required:
            print(f"  ✗ {var_name}: NOT SET (required)")
            missing.append(var_name)
        else:
            print(f"  ○ {var_name}: NOT SET (optional)")

    return missing


def check_alpaca_connection():
    """Test Alpaca API connection"""
    print("\nTesting Alpaca connection...")

    try:
        from alpaca.client import AlpacaClient
        client = AlpacaClient()

        if client.test_connection():
            print("  ✓ Alpaca connection successful")
            return True
        else:
            print("  ✗ Alpaca connection failed")
            return False
    except Exception as e:
        print(f"  ✗ Alpaca connection error: {e}")
        return False


def check_claude_connection():
    """Test Claude API connection"""
    print("\nTesting Claude connection...")

    try:
        from agent.core.reasoning import ReasoningEngine
        engine = ReasoningEngine()

        if engine.test_connection():
            print("  ✓ Claude connection successful")
            return True
        else:
            print("  ✗ Claude connection failed (API key may be invalid)")
            return False
    except Exception as e:
        print(f"  ✗ Claude connection error: {e}")
        return False


def main():
    print("=" * 60)
    print("AI Trading Agent - Setup Verification")
    print("=" * 60)

    # Check dependencies
    missing_deps = check_dependencies()

    if missing_deps:
        print(f"\n⚠️  Missing dependencies: {', '.join(missing_deps)}")
        print("\nInstall with:")
        print(f"  pip install {' '.join(missing_deps)}")
        print("\nOr install all requirements:")
        print("  pip install -r requirements.txt")
        return 1

    # Check environment
    missing_env = check_environment()

    if missing_env:
        print(f"\n⚠️  Missing environment variables: {', '.join(missing_env)}")
        print("\nCopy .env.example to .env and fill in the values:")
        print("  cp .env.example .env")
        print("  # Edit .env with your API keys")
        return 1

    # Test connections
    alpaca_ok = check_alpaca_connection()
    claude_ok = check_claude_connection()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if alpaca_ok and claude_ok:
        print("✓ All checks passed! You can run the agent with:")
        print("  python -m cli.main --paper")
        print("  python -m cli.main --dashboard")
        return 0
    else:
        print("⚠️  Some checks failed. Please fix the issues above.")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Setup verification failed: {e}")
        sys.exit(1)
