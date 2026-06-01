"""
Download external Chinese sentiment dictionaries and merge them into data/sentiment/.

Downloads from:
  1. BOSON Sentiment Dictionary (MIT) - github.com/InsightDataScience/BosonNLP
  2. NTUSD (Academic) - Academy Sinica NLP Lab

Usage:
    python scripts/download_sentiment_dicts.py
    python scripts/download_sentiment_dicts.py --skip-boson --skip-ntusd
    python scripts/download_sentiment_dicts.py --output data/sentiment
"""

import argparse
import logging
import os
import sys

# Use system python (not venv) for urllib in case venv pip is broken
try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError
except ImportError:
    from urllib2 import urlopen, Request, URLError

try:
    import ssl
except ImportError:
    ssl = None

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Default output directory (project root / data/sentiment)
_DEFAULT_OUTPUT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "sentiment")
)

# External dictionary sources (with fallback URLs)
_SOURCES = {
    "boson": {
        "urls": [
            "https://raw.githubusercontent.com/InsightDataScience/BosonNLP/master/SentimentDict/BosonNLP_sentiment_dict.txt",
            "https://cdn.jsdelivr.net/gh/InsightDataScience/BosonNLP@master/SentimentDict/BosonNLP_sentiment_dict.txt",
            "https://gitcode.com/Open-source-documentation-tutorial/4ac12/raw/main/BosonNLP_sentiment_score.txt",
            "https://bosonnlp.com/resources/BosonNLP_sentiment_score.zip",
        ],
        "description": "BOSON Sentiment Dictionary (~40,000 words, MIT)",
        "filename": "boson_sentiment.txt",
    },
    "ntusd_positive": {
        "urls": [
            "https://raw.githubusercontent.com/opencog-zhang/NTUSD/master/NTUSD_positive_unicode.txt",
            "https://raw.githubusercontent.com/dleetaiwan/Sentiment-Dictionary/master/ntusd_positive.txt",
            "https://raw.githubusercontent.com/iaspire/ntusd/master/ntusd_positive.txt",
        ],
        "description": "NTUSD Positive (~2,800 words, Academic)",
        "filename": "ntusd_positive.txt",
    },
    "ntusd_negative": {
        "urls": [
            "https://raw.githubusercontent.com/opencog-zhang/NTUSD/master/NTUSD_negative_unicode.txt",
            "https://raw.githubusercontent.com/dleetaiwan/Sentiment-Dictionary/master/ntusd_negative.txt",
            "https://raw.githubusercontent.com/iaspire/ntusd/master/ntusd_negative.txt",
        ],
        "description": "NTUSD Negative (~8,300 words, Academic)",
        "filename": "ntusd_negative.txt",
    },
    # English sentiment dictionaries
    "liu_positive": {
        "urls": [
            "https://raw.githubusercontent.com/jeffreybreen/twitter-sentiment-analysis-tutorial-201107/master/data/opinion-lexicon-English/positive-words.txt",
            "https://raw.githubusercontent.com/stdlib-js/datasets-liu-positive-opinion-words-en/master/data/words.txt",
        ],
        "description": "Bing Liu Opinion Lexicon - Positive (~2,000 words, Academic)",
        "filename": "liu_positive.txt",
    },
    "liu_negative": {
        "urls": [
            "https://raw.githubusercontent.com/jeffreybreen/twitter-sentiment-analysis-tutorial-201107/master/data/opinion-lexicon-English/negative-words.txt",
            "https://raw.githubusercontent.com/stdlib-js/datasets-liu-negative-opinion-words-en/master/data/words.txt",
        ],
        "description": "Bing Liu Opinion Lexicon - Negative (~4,800 words, Academic)",
        "filename": "liu_negative.txt",
    },
    "afinn": {
        "urls": [
            "https://raw.githubusercontent.com/fnielsen/afinn/master/afinn/data/AFINN-111.txt",
        ],
        "description": "AFINN Lexicon (~2,500 words with valence scores, Public Domain)",
        "filename": "afinn.txt",
    },
}


def download_file(url: str, dest_path: str) -> bool:
    """Download a file from URL to destination path.
    Tries multiple SSL approaches (verified, unverified, plain HTTP).
    Returns True on success, False on failure.
    """
    attempts = _build_download_attempts(url)
    for attempt_label, target_url, ctx in attempts:
        try:
            logger.info("  (%s) %s ...", attempt_label, target_url)
            if ctx is not None:
                resp = urlopen(target_url, timeout=30, context=ctx)
            else:
                resp = urlopen(target_url, timeout=30)
            content = resp.read().decode("utf-8")
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(content)
            lines = len([l for l in content.split("\n") if l.strip() and not l.startswith("#")])
            logger.info("  -> Saved %d entries to %s", lines, dest_path)
            return True
        except Exception as e:
            if "UNEXPECTED_EOF" in str(e) or "EOF occurred" in str(e) or "CERTIFICATE" in str(e):
                logger.info("  SSL issue, trying fallback...")
            else:
                logger.warning("  -> Failed: %s", str(e).split(".")[0][:80])
                return False
    return False


def _build_download_attempts(url: str):
    """Build list of (label, url, ssl_context) download attempts."""
    attempts = []
    # 1. Default SSL (verified)
    attempts.append(("https", url, None))
    # 2. Unverified SSL (bypasses cert issues, common in restricted networks)
    if ssl is not None:
        try:
            ctx = ssl._create_unverified_context()
            attempts.append(("https(unverified)", url, ctx))
        except Exception:
            pass
    # 3. Plain HTTP fallback (for networks that intercept HTTPS)
    if url.startswith("https://"):
        http_url = url.replace("https://", "http://", 1)
        attempts.append(("http", http_url, None))
    return attempts


def merge_file(src_path: str, target_set_path: str, polarity: str):
    """Merge downloaded dictionary entries into the existing .txt files.

    polarity: 'positive' or 'negative'
    """
    if not os.path.exists(src_path):
        logger.warning("  Source not found: %s", src_path)
        return 0

    with open(src_path, encoding="utf-8") as f:
        new_words = set(
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        )

    existing = set()
    if os.path.exists(target_set_path):
        with open(target_set_path, encoding="utf-8") as f:
            existing = set(
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            )

    added = new_words - existing
    if added:
        with open(target_set_path, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write(f"# Merged from external source ({os.path.basename(src_path)})\n")
            for word in sorted(added):
                f.write(f"{word}\n")

    logger.info(
        "  Merged %d new %s words into %s (was %d, now %d)",
        len(added),
        polarity,
        os.path.basename(target_set_path),
        len(existing),
        len(existing | added),
    )
    return len(added)


def main():
    parser = argparse.ArgumentParser(
        description="Download external Chinese sentiment dictionaries",
        epilog=(
            "If GitHub is unreachable (common in CN), use --boson-url to specify "
            "a mirror URL (e.g. Gitee, CSDN, or local HTTP server). "
            "The built-in ~1,700 word dictionary works without downloads."
        ),
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help=f"Output directory (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument("--skip-boson", action="store_true", help="Skip BOSON dictionary")
    parser.add_argument("--skip-ntusd", action="store_true", help="Skip NTUSD dictionaries")
    parser.add_argument("--skip-english", action="store_true",
                        help="Skip English dictionaries (Bing Liu, AFINN)")
    parser.add_argument("--merge-only", action="store_true",
                        help="Skip download, only merge existing downloaded files")
    parser.add_argument("--boson-url", help="Custom BOSON dictionary URL (for mirror/proxy)")
    parser.add_argument("--ntusd-url", help="Custom NTUSD dictionary base URL (for mirror/proxy)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    tmp_dir = os.path.join(args.output, "_downloads")
    os.makedirs(tmp_dir, exist_ok=True)

    downloads = []

    if not args.skip_boson:
        downloads.append(_SOURCES["boson"])
    if not args.skip_ntusd:
        downloads.append(_SOURCES["ntusd_positive"])
        downloads.append(_SOURCES["ntusd_negative"])
    if not args.skip_english:
        downloads.append(_SOURCES["liu_positive"])
        downloads.append(_SOURCES["liu_negative"])
        downloads.append(_SOURCES["afinn"])

    logger.info("Downloading sentiment dictionaries to: %s", tmp_dir)

    # Download
    if not args.merge_only:
        for src in downloads:
            dest = os.path.join(tmp_dir, src["filename"])
            logger.info("\n[%s] %s", src["filename"], src["description"])
            success = False

            # Try custom URL first (if provided via --boson-url / --ntusd-url)
            custom_url = None
            if "boson" in src["filename"] and args.boson_url:
                custom_url = args.boson_url
            elif "ntusd" in src["filename"] and args.ntusd_url:
                base = args.ntusd_url.rstrip("/")
                fname = src["filename"].replace("ntusd_", "")
                custom_url = f"{base}/{fname}"

            if custom_url:
                if download_file(custom_url, dest):
                    success = True

            # Try default URLs
            if not success:
                for url in src["urls"]:
                    if download_file(url, dest):
                        success = True
                        break

            if not success:
                logger.warning("  All URLs failed for %s", src["filename"])

    # Merge into existing dictionary
    logger.info("\nMerging into existing dictionary in: %s", args.output)

    positive_path_zh = os.path.join(args.output, "positive_zh.txt")
    negative_path_zh = os.path.join(args.output, "negative_zh.txt")
    positive_path_en = os.path.join(args.output, "positive_en.txt")
    negative_path_en = os.path.join(args.output, "negative_en.txt")

    total_added = 0

    # BOSON: contains both positive and negative
    boson_path = os.path.join(tmp_dir, _SOURCES["boson"]["filename"])
    if os.path.exists(boson_path):
        # BOSON format: word\tpolarity (pos/neg)
        boson_pos = set()
        boson_neg = set()
        with open(boson_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    word, pol = parts
                    if pol == "pos":
                        boson_pos.add(word)
                    elif pol == "neg":
                        boson_neg.add(word)

        # Merge positive (BOSON is Chinese, merge into _zh files)
        existing_pos = set()
        if os.path.exists(positive_path_zh):
            with open(positive_path_zh, encoding="utf-8") as f:
                existing_pos = set(
                    l.strip() for l in f if l.strip() and not l.startswith("#")
                )
        new_pos = boson_pos - existing_pos
        if new_pos:
            with open(positive_path_zh, "a", encoding="utf-8") as f:
                f.write("\n# Merged from BOSON sentiment dictionary\n")
                for word in sorted(new_pos):
                    f.write(f"{word}\n")
            total_added += len(new_pos)

        # Merge negative
        existing_neg = set()
        if os.path.exists(negative_path_zh):
            with open(negative_path_zh, encoding="utf-8") as f:
                existing_neg = set(
                    l.strip() for l in f if l.strip() and not l.startswith("#")
                )
        new_neg = boson_neg - existing_neg
        if new_neg:
            with open(negative_path_zh, "a", encoding="utf-8") as f:
                f.write("\n# Merged from BOSON sentiment dictionary\n")
                for word in sorted(new_neg):
                    f.write(f"{word}\n")
            total_added += len(new_neg)

        logger.info(
            "  BOSON: merged %d positive + %d negative = %d new words",
            len(new_pos), len(new_neg), len(new_pos) + len(new_neg),
        )

    # NTUSD positive (NTUSD is Chinese, merge into _zh files)
    ntusd_pos_path = os.path.join(tmp_dir, _SOURCES["ntusd_positive"]["filename"])
    if os.path.exists(ntusd_pos_path):
        total_added += merge_file(ntusd_pos_path, positive_path_zh, "positive")

    # NTUSD negative
    ntusd_neg_path = os.path.join(tmp_dir, _SOURCES["ntusd_negative"]["filename"])
    if os.path.exists(ntusd_neg_path):
        total_added += merge_file(ntusd_neg_path, negative_path_zh, "negative")

    # --- English dictionaries ---

    # Bing Liu positive: word-per-line, ; as comments
    liu_pos_path = os.path.join(tmp_dir, _SOURCES["liu_positive"]["filename"])
    if os.path.exists(liu_pos_path):
        words = set()
        with open(liu_pos_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith(";") and not s.startswith("#"):
                    words.add(s.lower())
        # Merge into positive_en.txt
        existing = set()
        if os.path.exists(positive_path_en):
            with open(positive_path_en, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        existing.add(s.lower())
        new_words = words - existing
        if new_words:
            with open(positive_path_en, "a", encoding="utf-8") as f:
                f.write("\n# Merged from Bing Liu Opinion Lexicon (positive)\n")
                for word in sorted(new_words):
                    f.write(f"{word}\n")
            total_added += len(new_words)
            logger.info("  Bing Liu positive: merged %d new words", len(new_words))

    # Bing Liu negative
    liu_neg_path = os.path.join(tmp_dir, _SOURCES["liu_negative"]["filename"])
    if os.path.exists(liu_neg_path):
        words = set()
        with open(liu_neg_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith(";") and not s.startswith("#"):
                    words.add(s.lower())
        existing = set()
        if os.path.exists(negative_path_en):
            with open(negative_path_en, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        existing.add(s.lower())
        new_words = words - existing
        if new_words:
            with open(negative_path_en, "a", encoding="utf-8") as f:
                f.write("\n# Merged from Bing Liu Opinion Lexicon (negative)\n")
                for word in sorted(new_words):
                    f.write(f"{word}\n")
            total_added += len(new_words)
            logger.info("  Bing Liu negative: merged %d new words", len(new_words))

    # AFINN: word\tscore format, positive score -> positive_en, negative -> negative_en
    afinn_path = os.path.join(tmp_dir, _SOURCES["afinn"]["filename"])
    if os.path.exists(afinn_path):
        afinn_pos = set()
        afinn_neg = set()
        with open(afinn_path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    word, score_str = parts
                    try:
                        score = int(score_str)
                    except ValueError:
                        continue
                    w = word.strip().lower()
                    if w:
                        if score > 0:
                            afinn_pos.add(w)
                        elif score < 0:
                            afinn_neg.add(w)

        # Merge positive
        existing_pos = set()
        if os.path.exists(positive_path_en):
            with open(positive_path_en, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        existing_pos.add(s.lower())
        new_pos = afinn_pos - existing_pos
        if new_pos:
            with open(positive_path_en, "a", encoding="utf-8") as f:
                f.write("\n# Merged from AFINN lexicon (positive)\n")
                for word in sorted(new_pos):
                    f.write(f"{word}\n")
            total_added += len(new_pos)

        # Merge negative
        existing_neg = set()
        if os.path.exists(negative_path_en):
            with open(negative_path_en, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        existing_neg.add(s.lower())
        new_neg = afinn_neg - existing_neg
        if new_neg:
            with open(negative_path_en, "a", encoding="utf-8") as f:
                f.write("\n# Merged from AFINN lexicon (negative)\n")
                for word in sorted(new_neg):
                    f.write(f"{word}\n")
            total_added += len(new_neg)

        logger.info(
            "  AFINN: merged %d positive + %d negative = %d new words",
            len(new_pos), len(new_neg), len(new_pos) + len(new_neg),
        )

    # If no external dictionaries were downloaded, remind user it's optional
    if total_added == 0:
        logger.info(
            "\nNote: built-in dictionary contains ~1,700 words (fully functional).\n"
            "External dictionaries are optional enhancements.\n"
            "\n"
            "Download manually from:\n"
            "  - Bing Liu Opinion Lexicon: https://github.com/jeffreybreen/twitter-sentiment-analysis-tutorial-201107\n"
            "  - AFINN: https://raw.githubusercontent.com/fnielsen/afinn/master/afinn/data/AFINN-111.txt\n"
            "  - BOSON (Chinese): https://github.com/InsightDataScience/BosonNLP\n"
            "  - NTUSD (Chinese): https://github.com/opencog-zhang/NTUSD\n"
            "\n"
            "Place downloaded files in data/sentiment/_downloads/ and run --merge-only"
        )

    logger.info("\nDone! Added %d new words to dictionary.", total_added)

    # Print final stats
    for lang in ["zh", "en"]:
        for name in [f"positive_{lang}.txt", f"negative_{lang}.txt",
                     f"intensifiers_{lang}.txt", f"negation_{lang}.txt"]:
            path = os.path.join(args.output, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    words = [
                        l.strip() for l in f
                        if l.strip() and not l.startswith("#")
                    ]
                if words:
                    logger.info("  %s: %d words", name, len(words))


if __name__ == "__main__":
    main()
