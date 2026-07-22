"""
Sentiment Analyzer
------------------
Uses VADER (Valence Aware Dictionary and sEntiment Reasoner) to score
social media posts and detect which crypto coins are being mentioned.
"""

import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ----------------------------------------------------------------
#  Coin keyword mapping  →  { SYMBOL: [keywords to detect] }
#  Add or remove coins here freely.
# ----------------------------------------------------------------
CRYPTO_KEYWORDS = {
    "BTC":   ["bitcoin", "btc", "$btc", "satoshi"],
    "ETH":   ["ethereum", "eth", "$eth", "ether"],
    "SOL":   ["solana", "sol", "$sol"],
    "DOGE":  ["dogecoin", "doge", "$doge"],
    "SHIB":  ["shiba", "shib", "$shib", "shiba inu"],
    "ADA":   ["cardano", "ada", "$ada"],
    "XRP":   ["ripple", "xrp", "$xrp"],
    "BNB":   ["binance coin", "bnb", "$bnb"],
    "AVAX":  ["avalanche", "avax", "$avax"],
    "MATIC": ["polygon", "matic", "$matic"],
    "DOT":   ["polkadot", "dot", "$dot"],
    "LINK":  ["chainlink", "link", "$link"],
    "LTC":   ["litecoin", "ltc", "$ltc"],
    "ATOM":  ["cosmos", "atom", "$atom"],
    "NEAR":  ["near protocol", "near", "$near"],
    "ICP":   ["internet computer", "icp", "$icp"],
    "TRX":   ["tron", "trx", "$trx"],
    "FIL":   ["filecoin", "fil", "$fil"],
    "HBAR":  ["hedera", "hbar", "$hbar"],
    "VET":   ["vechain", "vet", "$vet"],
}

# Generic crypto terms — if detected with no specific coin, we default to BTC
GENERIC_CRYPTO_TERMS = [
    "crypto", "cryptocurrency", "blockchain", "defi", "nft",
    "web3", "altcoin", "hodl", "moonshot", "digital currency",
    "digital asset", "coin", "token"
]

# Words that amplify positive sentiment in crypto context
CRYPTO_BOOSTER_WORDS = [
    "moon", "bullish", "buy", "long", "pump", "surge", "rally",
    "breakout", "all time high", "ath", "explosive", "skyrocket",
    "undervalued", "gem", "massive", "huge", "incredible"
]

class SentimentAnalyzer:
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()

    # ------------------------------------------------------------------
    def analyze(self, text: str) -> dict:
        """
        Analyze a post for crypto sentiment.

        Returns a dict:
          coins            – list of detected coin symbols (e.g. ["BTC", "ETH"])
          has_generic      – True if generic crypto terms detected (no specific coin)
          sentiment        – VADER compound score (-1.0 to +1.0)
          is_positive      – True if score >= SENTIMENT_THRESHOLD
          is_negative      – True if score <= -0.3
          confidence       – abs(sentiment), handy for ranking signals
          boosted          – True if crypto booster words found
        """
        lower = text.lower()

        # --- detect specific coins ---
        coins = []
        for symbol, keywords in CRYPTO_KEYWORDS.items():
            for kw in keywords:
                if kw in lower:
                    if symbol not in coins:
                        coins.append(symbol)
                    break

        # --- detect generic crypto terms ---
        has_generic = any(term in lower for term in GENERIC_CRYPTO_TERMS)

        # --- detect booster words ---
        boosted = any(word in lower for word in CRYPTO_BOOSTER_WORDS)

        # --- VADER sentiment ---
        scores   = self.vader.polarity_scores(text)
        compound = scores["compound"]

        # Slight boost if crypto booster words are present
        if boosted and compound > 0:
            compound = min(compound * 1.15, 1.0)

        from config import SENTIMENT_THRESHOLD
        return {
            "coins":       coins,
            "has_generic": has_generic,
            "sentiment":   round(compound, 4),
            "is_positive": compound >= SENTIMENT_THRESHOLD,
            "is_negative": compound <= -0.30,
            "confidence":  round(abs(compound), 4),
            "boosted":     boosted,
        }

    # ------------------------------------------------------------------
    def quick_check(self, text: str) -> bool:
        """Fast pre-filter: does this post mention crypto at all?"""
        lower = text.lower()
        for keywords in CRYPTO_KEYWORDS.values():
            for kw in keywords:
                if kw in lower:
                    return True
        return any(term in lower for term in GENERIC_CRYPTO_TERMS)
