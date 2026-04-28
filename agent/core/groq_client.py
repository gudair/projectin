"""
Groq Client for AI Analysis

Uses GPT-OSS 120B via Groq's fast inference API.
Free tier with generous rate limits.
"""

import os
import json
import httpx
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Try to load dotenv, but don't fail if not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


@dataclass
class GroqAnalysis:
    """Result of AI analysis"""
    action: str  # BUY, SELL, HOLD
    confidence: float  # 0.0 - 1.0
    reasoning: str
    risk_level: str  # LOW, MEDIUM, HIGH
    raw_response: str


class GroqClient:
    """
    Groq API client for GPT-OSS 120B inference.

    Much more capable than local Ollama because:
    - Full 120B parameter model
    - Runs on Groq LPUs (specialized AI hardware)
    - ~500 tok/s, 2x faster than Llama 3.3 70B
    """

    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    MODEL = "openai/gpt-oss-120b"  # Best model for analysis (updated Apr 2026)

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def analyze_trade(
        self,
        symbol: str,
        current_price: float,
        prev_day_change: float,
        day_range: float,
        rsi: float,
        support_distance: float,
        market_trend: str,
        has_position: bool = False,
        position_pnl: float = 0.0,
        news_sentiment: Optional[str] = None,
    ) -> GroqAnalysis:
        """
        Analyze a potential trade using AI.

        Returns a structured analysis with action, confidence, and reasoning.
        """

        # Build the prompt
        position_status = f"HOLDING position with {position_pnl:+.1%} P&L" if has_position else "NO position"

        # Add news context if available
        news_context = ""
        if news_sentiment:
            news_context = f"\nNEWS SENTIMENT TODAY: {news_sentiment}"

        prompt = f"""You are an aggressive day trading analyst. Analyze this setup and give a trading decision.

SYMBOL: {symbol}
CURRENT PRICE: ${current_price:.2f}
PREVIOUS DAY: {prev_day_change:+.1%} ({"RED" if prev_day_change < 0 else "GREEN"})
TODAY'S RANGE: {day_range:.1%}
RSI(14): {rsi:.1f}
DISTANCE TO SUPPORT: {support_distance:.1%}
MARKET TREND: {market_trend}
POSITION: {position_status}{news_context}

STRATEGY RULES:
- Entry: Buy after red day (-1%+), high volatility (2%+ range), RSI < 45
- Exit: 2% stop loss, 2% trailing stop, 10% take profit
- This is an AGGRESSIVE dip-buying strategy

Analyze and respond in this EXACT JSON format:
{{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0-1.0, "risk_level": "LOW" or "MEDIUM" or "HIGH", "reasoning": "brief explanation"}}

JSON response:"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.BASE_URL,
                    headers=self.headers,
                    json={
                        "model": self.MODEL,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 300,
                    }
                )

                if response.status_code != 200:
                    logger.error(f"Groq API error: {response.status_code} - {response.text}")
                    return self._default_analysis("API error")

                data = response.json()
                raw_response = data["choices"][0]["message"]["content"].strip()

                # Parse JSON response
                return self._parse_response(raw_response)

        except httpx.TimeoutException:
            logger.error("Groq API timeout")
            return self._default_analysis("Timeout")
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return self._default_analysis(str(e))

    def _parse_response(self, raw: str) -> GroqAnalysis:
        """Parse the JSON response from the model"""
        import re
        try:
            # Clean up response - find JSON in response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = raw[start:end]
                # Try direct parse first (handles well-formed JSON)
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    # Some models emit unescaped newlines inside string values; flatten them
                    json_str = re.sub(r'\n\s*', ' ', json_str)
                    data = json.loads(json_str)

                return GroqAnalysis(
                    action=data.get("action", "HOLD").upper(),
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning", "No reasoning provided"),
                    risk_level=data.get("risk_level", "MEDIUM").upper(),
                    raw_response=raw,
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse Groq response: {e}")

        return self._default_analysis(f"Parse error: {raw[:100]}")

    def _default_analysis(self, reason: str) -> GroqAnalysis:
        """Return a default HOLD analysis on error"""
        return GroqAnalysis(
            action="HOLD",
            confidence=0.0,
            reasoning=f"Error: {reason}",
            risk_level="HIGH",
            raw_response="",
        )

    async def test_connection(self) -> bool:
        """Test the Groq API connection"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.BASE_URL,
                    headers=self.headers,
                    json={
                        "model": self.MODEL,
                        "messages": [{"role": "user", "content": "Say 'OK' if you work"}],
                        "max_tokens": 10,
                    }
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Groq connection test failed: {e}")
            return False


# Quick test
if __name__ == "__main__":
    import asyncio

    async def test():
        client = GroqClient()

        print("Testing Groq connection...")
        if await client.test_connection():
            print("✅ Connected to Groq!")

            print("\nTesting trade analysis...")
            result = await client.analyze_trade(
                symbol="NVDA",
                current_price=180.50,
                prev_day_change=-0.025,
                day_range=0.035,
                rsi=38.5,
                support_distance=0.02,
                market_trend="NEUTRAL",
            )

            print(f"Action: {result.action}")
            print(f"Confidence: {result.confidence:.0%}")
            print(f"Risk: {result.risk_level}")
            print(f"Reasoning: {result.reasoning}")
        else:
            print("❌ Failed to connect to Groq")

    asyncio.run(test())
