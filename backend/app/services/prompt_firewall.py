import re
from dataclasses import dataclass


@dataclass
class FirewallResult:
    safe: bool
    risk_score: float  # 0.0 to 1.0
    threats_detected: list[str]
    sanitized_prompt: str


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
        prompt_lower = prompt.lower()

        for compiled_re, threat_name, risk in cls.INJECTION_PATTERNS:
            if compiled_re.search(prompt_lower):
                threats.append(threat_name)
                max_risk = max(max_risk, risk)

        for compiled_re, data_type in cls.SENSITIVE_DATA_PATTERNS:
            if compiled_re.search(prompt):
                threats.append(data_type)
                max_risk = max(max_risk, 0.5)

        # Heuristic: unusual ratio of special characters
        if len(prompt) > 50:
            special_ratio = sum(1 for c in prompt if not c.isalnum() and c != ' ') / len(prompt)
            if special_ratio > 0.3:
                threats.append("high_special_char_ratio")
                max_risk = max(max_risk, 0.6)

        # Heuristic: extremely long prompts (possible payload)
        if len(prompt) > 10000:
            threats.append("abnormal_length")
            max_risk = max(max_risk, 0.5)

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