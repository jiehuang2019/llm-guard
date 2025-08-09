"""
pip install llm-guard
# Optional (if you plan to call OpenAI):
# pip install openai
"""
from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

# ---- Try to use llm-guard's Vault + detectors; if not found, we'll fallback ----
try:
    from llm_guard.vault import Vault as LGVault
    # detector names can differ by release; try a few common ones
    try:
        from llm_guard.detectors import (
            VaultExactMatchDetector,
            VaultRegexDetector,
        )
        _HAVE_LLM_GUARD = True
    except Exception:
        _HAVE_LLM_GUARD = False
except Exception:
    _HAVE_LLM_GUARD = False


# ------------------------------
# Logging helper
# ------------------------------
@dataclass
class DetectionEvent:
    when: float
    phase: str               # "input" or "output"
    matches: List[Dict]      # list of {type, key, match, span}
    redacted: bool
    original_preview: str
    redacted_preview: str

class Auditor:
    def __init__(self, path: str = "detections.log.jsonl"):
        self.path = Path(path)

    def log(self, evt: DetectionEvent):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(evt), ensure_ascii=False) + "\n")


# ------------------------------
# Vault loading
# ------------------------------
class Vault:
    """Thin wrapper so our code works with or without llm-guard."""
    def __init__(self, data: Dict):
        self.data = data

    @classmethod
    def from_file(cls, path: str | Path) -> "Vault":
        if _HAVE_LLM_GUARD:
            # real llm-guard Vault
            vault = LGVault.from_file(str(path))
            return cls({"__llm_guard_vault__": vault})
        # fallback
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    # Helpers to read stored items
    def get_list(self, key: str) -> List[str]:
        if "__llm_guard_vault__" in self.data:
            v = self.data["__llm_guard_vault__"]
            # llm-guard Vault typically exposes dict-like access; adapt if needed
            return list(v.get(key, []))
        return list(self.data.get(key, []))

    def get_regexes(self) -> Dict[str, str]:
        if "__llm_guard_vault__" in self.data:
            v = self.data["__llm_guard_vault__"]
            return dict(v.get("regexes", {}))
        return dict(self.data.get("regexes", {}))


# ------------------------------
# Detectors (llm-guard or fallback)
# ------------------------------
class DetectorResult(Dict):
    """Each match: {'type': 'exact'|'regex', 'key': 'api_keys'|name, 'match': str, 'span': (start, end)}"""

def scan_with_llm_guard(text: str, vault: Vault) -> List[DetectorResult]:
    """Use llm-guard’s detectors if available."""
    results: List[DetectorResult] = []
    # Exact lists
    if _HAVE_LLM_GUARD:
        try:
            v = vault.data["__llm_guard_vault__"]
            for key in ["api_keys", "emails"]:
                values = list(v.get(key, []))
                if values:
                    det = VaultExactMatchDetector(vault=v, vault_key=key)
                    found = det.detect(text)  # expected to return matches; adapt if your version differs
                    for m in found:
                        results.append({
                            "type": "exact",
                            "key": key,
                            "match": m.get("match", ""),
                            "span": m.get("span", (-1, -1)),
                        })
        except Exception:
            pass

        # Regexes
        try:
            v = vault.data["__llm_guard_vault__"]
            regexes = dict(v.get("regexes", {}))
            if regexes:
                det = VaultRegexDetector(vault=v, vault_key="regexes")
                found = det.detect(text)
                for m in found:
                    results.append({
                        "type": "regex",
                        "key": m.get("name", "regex"),
                        "match": m.get("match", ""),
                        "span": m.get("span", (-1, -1)),
                    })
        except Exception:
            pass

    return results

def scan_fallback(text: str, vault: Vault) -> List[DetectorResult]:
    """If llm-guard detector signatures differ, do a simple local scan."""
    out: List[DetectorResult] = []
    # exact lists
    for key in ["api_keys", "emails"]:
        for token in vault.get_list(key):
            start = 0
            while True:
                idx = text.find(token, start)
                if idx == -1:
                    break
                out.append({"type": "exact", "key": key, "match": token, "span": (idx, idx + len(token))})
                start = idx + len(token)
    # regexes
    for name, pattern in vault.get_regexes().items():
        for m in re.finditer(pattern, text):
            out.append({"type": "regex", "key": name, "match": m.group(0), "span": (m.start(), m.end())})
    return out

def scan_text(text: str, vault: Vault) -> List[DetectorResult]:
    results = []
    if _HAVE_LLM_GUARD:
        results.extend(scan_with_llm_guard(text, vault))
    # Always run fallback too (covers cases where some keys weren’t scanned)
    results.extend(scan_fallback(text, vault))
    # Dedup by (span, match)
    uniq = {}
    for r in results:
        uniq[(r["span"], r["match"])] = r
    return list(uniq.values())


# ------------------------------
# Redaction
# ------------------------------
REDACTION_TOKEN = "[REDACTED]"

def redact_text(text: str, matches: List[DetectorResult]) -> str:
    if not matches:
        return text
    # Replace from end to start so spans stay valid
    s = text
    for _, r in sorted(enumerate(matches), key=lambda x: x[1]["span"][0], reverse=True):
        start, end = r["span"]
        if 0 <= start < end <= len(s):
            s = s[:start] + REDACTION_TOKEN + s[end:]
    return s


# ------------------------------
# Example pipeline
# ------------------------------
def main():
    auditor = Auditor("detections.log.jsonl")
    vault = Vault.from_file("secrets_vault.json")

    # ---- Phase 1: scan/redact INPUT (from user) ----
    user_input = "Please summarize this and email the result to admin@example.com. My API key is sk-live-abc123."
    in_matches = scan_text(user_input, vault)
    user_input_redacted = redact_text(user_input, in_matches)

    auditor.log(DetectionEvent(
        when=time.time(),
        phase="input",
        matches=in_matches,
        redacted=bool(in_matches),
        original_preview=user_input[:200],
        redacted_preview=user_input_redacted[:200],
    ))

    # You would now pass user_input_redacted to your LLM instead of the raw input.
    # For demo, we’ll fake an LLM response that leaks something:
    llm_output = (
        "Summary: ... Contact us at careers@company.com. "
        "By the way, here is a suspicious number 123-45-6789."
    )

    # ---- Phase 2: scan/redact OUTPUT (from LLM) ----
    out_matches = scan_text(llm_output, vault)
    llm_output_redacted = redact_text(llm_output, out_matches)

    auditor.log(DetectionEvent(
        when=time.time(),
        phase="output",
        matches=out_matches,
        redacted=bool(out_matches),
        original_preview=llm_output[:200],
        redacted_preview=llm_output_redacted[:200],
    ))

    print("=== INPUT (redacted) ===")
    print(user_input_redacted)
    print("\n=== OUTPUT (redacted) ===")
    print(llm_output_redacted)
    print("\n=== DETECTIONS (counts) ===")
    print(f"input:  {len(in_matches)}  | output: {len(out_matches)}")
    print("\nLogged events -> detections.log.jsonl")


if __name__ == "__main__":
    main()

