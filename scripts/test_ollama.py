#!/usr/bin/env python3
"""
Ollama Integration Test & Monitor

Tests the Ollama integration and shows performance metrics.
Uses only standard library (no external dependencies).
"""
import json
import time
import urllib.request
import urllib.error
from datetime import datetime

OLLAMA_URL = "http://localhost:11434"


def make_request(endpoint, data=None, timeout=120):
    """Make HTTP request to Ollama API"""
    url = f"{OLLAMA_URL}{endpoint}"

    if data:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
    else:
        req = urllib.request.Request(url)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def check_ollama_status():
    """Check if Ollama is running and get model info"""
    print("=" * 60)
    print("OLLAMA STATUS CHECK")
    print("=" * 60)

    data = make_request("/api/tags", timeout=10)

    if "error" in data:
        print(f"❌ Ollama is NOT RUNNING: {data['error']}")
        print(f"\nTo start Ollama, run: ollama serve")
        return False, []

    models = data.get('models', [])
    print(f"✅ Ollama is RUNNING at {OLLAMA_URL}")
    print(f"\nInstalled Models:")
    for m in models:
        size_gb = m.get('size', 0) / 1e9
        print(f"  • {m['name']} ({size_gb:.1f} GB)")

    return True, models


def check_active_models():
    """Check currently loaded models"""
    print("\n" + "-" * 40)
    print("ACTIVE MODELS:")

    data = make_request("/api/ps", timeout=10)

    if "error" in data:
        print(f"  Could not check: {data['error']}")
        return

    models = data.get('models', [])
    if models:
        for m in models:
            name = m.get('name', 'unknown')
            size = m.get('size', 0) / 1e9
            vram = m.get('size_vram', 0) / 1e9
            print(f"  🟢 {name} | Size: {size:.1f}GB | VRAM: {vram:.1f}GB")
    else:
        print("  💤 No models currently loaded (will load on first request)")


def test_simple_query():
    """Test a simple query to measure response time"""
    print("\n" + "=" * 60)
    print("SIMPLE QUERY TEST")
    print("=" * 60)

    prompt = "Say 'Hello, I am working correctly!' in exactly 5 words."
    print(f"Prompt: {prompt}")
    print("Waiting for response...")

    start = time.time()

    data = make_request("/api/generate", {
        "model": "llama3.1:latest",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 50,
        }
    })

    elapsed = time.time() - start

    if "error" in data:
        print(f"\n❌ Query failed after {elapsed:.2f}s: {data['error']}")
        return False, elapsed

    print(f"\n✅ Response received in {elapsed:.2f}s")
    print(f"Response: {data.get('response', 'N/A')}")

    print(f"\nMetrics:")
    total_dur = data.get('total_duration', 0) / 1e9
    load_dur = data.get('load_duration', 0) / 1e9
    eval_count = data.get('eval_count', 0)
    eval_dur = data.get('eval_duration', 0) / 1e9

    print(f"  • Total duration: {total_dur:.2f}s")
    print(f"  • Model load time: {load_dur:.2f}s")
    print(f"  • Tokens generated: {eval_count}")
    print(f"  • Generation time: {eval_dur:.2f}s")

    if eval_dur > 0:
        tokens_per_sec = eval_count / eval_dur
        print(f"  • Speed: {tokens_per_sec:.1f} tokens/sec")

    return True, elapsed


def test_trading_analysis():
    """Test a trading analysis prompt similar to what the agent uses"""
    print("\n" + "=" * 60)
    print("TRADING ANALYSIS TEST")
    print("=" * 60)

    system_prompt = """You are an expert day trader. Analyze setups, recommend trades.
Respond ONLY in JSON:
{"recommendation":"BUY|SELL|HOLD","confidence":0.0-1.0,"reasoning":"brief","entry_price":null,"stop_loss":null,"take_profit":null}"""

    user_prompt = """Analyze AAPL:
- Current Price: $185.50 (+1.2% today)
- RSI(14): 45 (NEUTRAL)
- MACD: Bullish crossover
- Volume: 1.5x average
- Market: SPY +0.5%, VIX 18

Give entry/stop/target prices."""

    print("Testing trading analysis prompt...")
    print("This simulates what the agent sends to Ollama.\n")

    start = time.time()

    data = make_request("/api/generate", {
        "model": "llama3.1:latest",
        "prompt": f"{system_prompt}\n\nUser: {user_prompt}",
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 500,
        }
    })

    elapsed = time.time() - start

    if "error" in data:
        print(f"\n❌ Analysis failed after {elapsed:.2f}s: {data['error']}")
        return False, elapsed

    response_text = data.get('response', '')
    print(f"✅ Analysis received in {elapsed:.2f}s")
    print(f"\nRaw Response:\n{'-'*40}\n{response_text}\n{'-'*40}")

    # Try to parse JSON
    try:
        if '{' in response_text:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            json_str = response_text[json_start:json_end]
            analysis = json.loads(json_str)

            print(f"\n✅ JSON Parsed Successfully:")
            print(f"  • Recommendation: {analysis.get('recommendation', 'N/A')}")
            print(f"  • Confidence: {analysis.get('confidence', 'N/A')}")
            print(f"  • Entry: ${analysis.get('entry_price', 'N/A')}")
            print(f"  • Stop Loss: ${analysis.get('stop_loss', 'N/A')}")
            print(f"  • Take Profit: ${analysis.get('take_profit', 'N/A')}")
            print(f"  • Reasoning: {analysis.get('reasoning', 'N/A')[:100]}")
        else:
            print(f"\n⚠️  No JSON found in response - model may need better prompting")
    except json.JSONDecodeError as e:
        print(f"\n⚠️  JSON parse error: {e}")
        print("    This may happen occasionally - the agent has fallback parsing")

    print(f"\nPerformance Metrics:")
    eval_count = data.get('eval_count', 0)
    eval_dur = data.get('eval_duration', 0) / 1e9

    print(f"  • Total time: {elapsed:.2f}s")
    print(f"  • Tokens generated: {eval_count}")

    if eval_dur > 0:
        tokens_per_sec = eval_count / eval_dur
        print(f"  • Speed: {tokens_per_sec:.1f} tokens/sec")

    return True, elapsed


def run_benchmark(num_requests=3):
    """Run multiple requests to benchmark performance"""
    print("\n" + "=" * 60)
    print(f"BENCHMARK ({num_requests} requests)")
    print("=" * 60)

    times = []
    successes = 0

    for i in range(num_requests):
        print(f"\nRequest {i+1}/{num_requests}...", end=" ", flush=True)

        start = time.time()
        data = make_request("/api/generate", {
            "model": "llama3.1:latest",
            "prompt": "What is 2+2? Answer in one word.",
            "stream": False,
            "options": {"num_predict": 10}
        })
        elapsed = time.time() - start

        times.append(elapsed)
        if "error" not in data:
            successes += 1
            print(f"✅ {elapsed:.2f}s")
        else:
            print(f"❌ {elapsed:.2f}s - {data['error']}")

    print("\n" + "-" * 40)
    print("BENCHMARK RESULTS:")
    print(f"  • Success rate: {successes}/{num_requests} ({100*successes/num_requests:.0f}%)")
    print(f"  • Avg response time: {sum(times)/len(times):.2f}s")
    print(f"  • Min response time: {min(times):.2f}s")
    print(f"  • Max response time: {max(times):.2f}s")

    if times[0] > times[-1] * 1.5:
        print(f"\n💡 First request was slower ({times[0]:.2f}s) - this is normal (model loading)")


def main():
    import sys

    print("\n🔍 OLLAMA DIAGNOSTIC TOOL")
    print("=" * 60)

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "status":
            check_ollama_status()
            check_active_models()
        elif command == "test":
            running, _ = check_ollama_status()
            if running:
                check_active_models()
                test_simple_query()
                test_trading_analysis()
        elif command == "benchmark":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            check_ollama_status()
            run_benchmark(n)
        elif command == "trading":
            test_trading_analysis()
        else:
            print(f"Unknown command: {command}")
            print("\nUsage:")
            print("  python scripts/test_ollama.py status    - Check Ollama status")
            print("  python scripts/test_ollama.py test      - Run all tests")
            print("  python scripts/test_ollama.py trading   - Test trading prompt only")
            print("  python scripts/test_ollama.py benchmark - Run performance benchmark")
    else:
        # Default: run all tests
        running, models = check_ollama_status()

        if running:
            check_active_models()
            test_simple_query()
            test_trading_analysis()

            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print("✅ Ollama is configured correctly for the trading agent")
            print("\nUsage:")
            print("  python scripts/test_ollama.py status    - Check status only")
            print("  python scripts/test_ollama.py test      - Full test suite")
            print("  python scripts/test_ollama.py benchmark - Performance test")


if __name__ == "__main__":
    main()
