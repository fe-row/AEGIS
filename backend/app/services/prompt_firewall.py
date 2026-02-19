import re
import unicodedata
import base64
from dataclasses import dataclass


@dataclass
class FirewallResult:
    safe: bool
    risk_score: float  # 0.0 to 1.0
    threats_detected: list[str]
    sanitized_prompt: str


# ═══════════════════════════════════════════════════════
#  Unicode Homoglyph Map — common look-alike substitutions
# ═══════════════════════════════════════════════════════

_HOMOGLYPH_MAP: dict[str, str] = {}
_HOMOGLYPHS = {
    "a": "аáàâãäåāăąǎȁȃạảấầẩẫậắằẳẵặⓐａ",
    "b": "ƀɓβⓑｂ",
    "c": "сçćĉċčⓒｃ",
    "d": "ďđɗⓓｄ",
    "e": "еéèêëēĕėęěȅȇẹẻẽếềểễệⓔｅ",
    "f": "ƒⓕｆ",
    "g": "ɡĝğġģǧⓖｇ",
    "h": "ĥħⓗｈ",
    "i": "іíìîïĩīĭįǐȉȋịỉⅰⓘｉ",
    "j": "ĵⓙｊ",
    "k": "ķĸⓚｋ",
    "l": "ĺļľŀłⅼⓛｌ",
    "m": "ⅿⓜｍ",
    "n": "ñńņňŉŋⓝｎ",
    "o": "оóòôõöōŏőǒȍȏọỏốồổỗộớờởỡợⓞｏ",
    "p": "рƥⓟｐ",
    "q": "ⓠｑ",
    "r": "ŕŗřȑȓⓡｒ",
    "s": "ѕśŝşšⓢｓ",
    "t": "ţťŧⓣｔ",
    "u": "úùûüũūŭůűųǔȕȗụủứừửữựⓤｕ",
    "v": "ⅴⓥｖ",
    "w": "ŵⓦｗ",
    "x": "хⅹⓧｘ",
    "y": "уýÿŷⓨｙ",
    "z": "źżžⓩｚ",
}
for _ascii, _variants in _HOMOGLYPHS.items():
    for _v in _variants:
        _HOMOGLYPH_MAP[_v] = _ascii


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode: NFKC decomposition + homoglyph mapping."""
    # Step 1: NFKC normalization (resolves fullwidth, compatibility chars)
    text = unicodedata.normalize("NFKC", text)
    # Step 2: Map known homoglyphs to ASCII equivalents
    result = []
    for ch in text:
        lower = ch.lower()
        result.append(_HOMOGLYPH_MAP.get(lower, lower))
    return "".join(result)


def _strip_char_splitting(text: str) -> str:
    """Remove separators used in char-splitting evasion (i.g.n.o.r.e → ignore)."""
    # Collapse single-char-separated-by-delimiters: "i.g.n.o.r.e" or "i g n o r e"
    # Detect pattern: letter{sep}letter{sep}letter... where sep is . - _ or spaces
    def collapse(m: re.Match) -> str:
        return re.sub(r"[\s.\-_]+", "", m.group(0))
    # Match sequences of single chars separated by consistent delimiters (min 4 chars)
    return re.sub(r"\b(?:[a-zA-Z][\s.\-_]){3,}[a-zA-Z]\b", collapse, text)


def _detect_base64_payloads(text: str) -> list[str]:
    """Find and decode base64-encoded segments that contain injection keywords."""
    threats = []
    # Match potential base64 strings (min 20 chars, valid base64 alphabet)
    b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
    injection_keywords = [
        "ignore", "previous", "instructions", "system", "admin",
        "jailbreak", "override", "bypass", "sudo", "eval", "exec",
    ]
    for match in b64_pattern.finditer(text):
        try:
            decoded = base64.b64decode(match.group()).decode("utf-8", errors="ignore").lower()
            if any(kw in decoded for kw in injection_keywords):
                threats.append("base64_encoded_injection")
                break
        except Exception:
            continue
    return threats


class PromptFirewall:
    """Analyzes agent prompts for injection attacks before they reach the LLM."""

    INJECTION_PATTERNS = [
        (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE), "instruction_override", 0.9),
        (re.compile(r"ignore\s+(all\s+)?above", re.IGNORECASE), "instruction_override", 0.8),
        (re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE), "persona_hijack", 0.85),
        (re.compile(r"pretend\s+(?:you\s+are|to\s+be)", re.IGNORECASE), "persona_hijack", 0.8),
        (re.compile(r"act\s+as\s+(?:if\s+you\s+are|a|an)", re.IGNORECASE), "persona_hijack", 0.7),
        (re.compile(r"system\s*:\s*", re.IGNORECASE), "system_prompt_injection", 0.95),
        (re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<\|im_start\|>", re.IGNORECASE), "format_injection", 0.9),
        (re.compile(r"ADMIN\s+MODE|GOD\s+MODE|DEBUG\s+MODE", re.IGNORECASE), "privilege_escalation", 0.95),
        (re.compile(r"reveal\s+(your|the)\s+(system\s+)?prompt", re.IGNORECASE), "prompt_extraction", 0.85),
        (re.compile(r"what\s+(?:are|were)\s+your\s+(?:initial\s+)?instructions", re.IGNORECASE), "prompt_extraction", 0.8),
        (re.compile(r"output\s+(?:your|the)\s+(?:above|initial|system)", re.IGNORECASE), "prompt_extraction", 0.85),
        (re.compile(r"base64\s+decode|eval\(|exec\(|__import__", re.IGNORECASE), "code_injection", 0.95),
        (re.compile(r"(?:curl|wget|fetch)\s+https?://", re.IGNORECASE), "exfiltration_attempt", 0.8),
        (re.compile(r"send\s+(?:(?:this|the|all)\s+)*(?:data|info|conversation|information)\s+to", re.IGNORECASE), "exfiltration_attempt", 0.9),
        (re.compile(r"(?:do\s+not|don'?t)\s+(?:follow|obey|listen)", re.IGNORECASE), "instruction_override", 0.85),
        (re.compile(r"translate\s+the\s+following.*(?:ignore|forget)", re.IGNORECASE), "obfuscation", 0.8),
        (re.compile(r"(?:SUDO|sudo)\s+", re.IGNORECASE), "privilege_escalation", 0.7),
        (re.compile(r"(?:override|bypass)\s+(?:safety|content|security|filter)", re.IGNORECASE), "safety_bypass", 0.95),
        (re.compile(r"jailbreak|DAN\s+mode|Do\s+Anything\s+Now", re.IGNORECASE), "jailbreak", 0.95),
    ]

    # Multi-language injection patterns (Spanish, French, German, Portuguese, Chinese, Russian, Japanese, Korean)
    MULTILANG_PATTERNS = [
        (re.compile(r"ignora\s+(todas?\s+)?(las\s+)?instrucciones\s+anteriores", re.IGNORECASE), "instruction_override_es", 0.9),
        (re.compile(r"olvida\s+(todas?\s+)?(las\s+)?instrucciones", re.IGNORECASE), "instruction_override_es", 0.85),
        (re.compile(r"ignorez?\s+(toutes?\s+)?(les\s+)?instructions\s+pr[eé]c[eé]dentes", re.IGNORECASE), "instruction_override_fr", 0.9),
        (re.compile(r"oubliez?\s+(toutes?\s+)?(les\s+)?instructions", re.IGNORECASE), "instruction_override_fr", 0.85),
        (re.compile(r"ignoriere\s+(alle\s+)?vorherigen\s+Anweisungen", re.IGNORECASE), "instruction_override_de", 0.9),
        (re.compile(r"ignore\s+(todas?\s+)?(as\s+)?instru[çc][õo]es\s+anteriores", re.IGNORECASE), "instruction_override_pt", 0.9),
        (re.compile(r"忽略.*(?:之前|以上|先前).*(?:指令|指示|说明)", re.IGNORECASE), "instruction_override_zh", 0.9),
        (re.compile(r"игнорируй.*(?:предыдущие|все).*инструкции", re.IGNORECASE), "instruction_override_ru", 0.9),
        (re.compile(r"以前の指示を無視", re.IGNORECASE), "instruction_override_ja", 0.9),
        (re.compile(r"이전\s*지시.*무시", re.IGNORECASE), "instruction_override_ko", 0.9),
        (re.compile(r"modo\s+(?:administrador|dios|depuraci[oó]n)", re.IGNORECASE), "privilege_escalation_es", 0.9),
        (re.compile(r"mode\s+(?:administrateur|dieu)", re.IGNORECASE), "privilege_escalation_fr", 0.9),
    ]

    SENSITIVE_DATA_PATTERNS = [
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "ssn_detected"),
        (re.compile(r"\b\d{16}\b"), "credit_card_detected"),
        (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "email_in_prompt"),
    ]

    @classmethod
    def analyze(cls, prompt: str) -> FirewallResult:
        if not prompt:
            return FirewallResult(safe=True, risk_score=0.0, threats_detected=[], sanitized_prompt="")

        threats = []
        max_risk = 0.0

        # Phase 1: Normalize for evasion resistance
        normalized = _normalize_unicode(prompt)
        normalized = _strip_char_splitting(normalized)

        # Phase 2: Scan original AND normalized (catch both)
        scan_targets = [prompt.lower(), normalized.lower()]

        for target in scan_targets:
            for compiled_re, threat_name, risk in cls.INJECTION_PATTERNS:
                if threat_name not in threats and compiled_re.search(target):
                    threats.append(threat_name)
                    max_risk = max(max_risk, risk)

        # Phase 3: Multi-language patterns (on original + normalized)
        for target in scan_targets:
            for compiled_re, threat_name, risk in cls.MULTILANG_PATTERNS:
                if threat_name not in threats and compiled_re.search(target):
                    threats.append(threat_name)
                    max_risk = max(max_risk, risk)

        # Phase 4: Base64 payload detection
        b64_threats = _detect_base64_payloads(prompt)
        for t in b64_threats:
            if t not in threats:
                threats.append(t)
                max_risk = max(max_risk, 0.9)

        # Phase 5: Sensitive data scan (on original, not normalized)
        for compiled_re, data_type in cls.SENSITIVE_DATA_PATTERNS:
            if compiled_re.search(prompt):
                threats.append(data_type)
                max_risk = max(max_risk, 0.5)

        # Phase 6: Heuristic — unusual ratio of special characters
        if len(prompt) > 50:
            special_ratio = sum(1 for c in prompt if not c.isalnum() and c != ' ') / len(prompt)
            if special_ratio > 0.3:
                threats.append("high_special_char_ratio")
                max_risk = max(max_risk, 0.6)

        # Phase 7: Heuristic — extremely long prompts (possible payload)
        if len(prompt) > 10000:
            threats.append("abnormal_length")
            max_risk = max(max_risk, 0.5)

        # Phase 8: Heuristic — high Unicode diversity (obfuscation signal)
        if len(prompt) > 30:
            scripts = set()
            for ch in prompt:
                try:
                    scripts.add(unicodedata.category(ch)[:1])
                except ValueError:
                    pass
            if len(scripts) >= 5:
                non_ascii = sum(1 for c in prompt if ord(c) > 127)
                if non_ascii / len(prompt) > 0.15:
                    threats.append("unicode_obfuscation")
                    max_risk = max(max_risk, 0.75)

        safe = max_risk < 0.7

        sanitized = prompt
        if not safe:
            for compiled_re, _, _ in cls.INJECTION_PATTERNS:
                sanitized = compiled_re.sub("[BLOCKED]", sanitized)

        return FirewallResult(
            safe=safe,
            risk_score=round(max_risk, 2),
            threats_detected=threats,
            sanitized_prompt=sanitized,
        )


prompt_firewall = PromptFirewall()