import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.auth_service import list_chat_messages, list_documents


SAFETY_VIOLATION_KEYWORDS = (
    "violation",
    "breach",
    "non-compliance",
    "failed",
    "injured",
    "fatality",
    "accident",
    "hazard",
    "unsafe",
)

EQUIPMENT_FAILURE_KEYWORDS = (
    "failure",
    "breakdown",
    "malfunction",
    "damaged",
    "faulty",
)

HAZARD_KEYWORDS = (
    "hazard",
    "unsafe",
    "injured",
    "fatality",
    "accident",
    "fire",
    "gas",
    "methane",
    "roof fall",
    "explosion",
    "inundation",
    "blasting",
)

INCIDENT_MARKERS = {
    "accident",
    "fatal",
    "fatality",
    "fatalities",
    "explosion",
    "inundation",
    "roof fall",
    "firedamp",
    "fire damp",
    "gas explosion",
    "colliery",
}

MINE_TERMS = {
    "hazards": {
        "roof fall", "fall of roof", "inundation", "explosion", "fire", "gas",
        "methane", "ventilation", "dust", "haulage", "machinery", "blasting",
        "electrical", "fatal", "death", "injury", "accident", "collapse",
    },
    "actions": {
        "notice", "report", "inspect", "inquiry", "training", "evacuate",
        "isolate", "lockout", "medical", "rescue", "preserve", "manager",
        "owner", "agent", "inspector", "form", "register", "maintenance",
    },
    "equipment": {
        "air compressor", "boiler", "cage", "compressor", "conveyor",
        "diesel engine", "diesel loco", "drill", "dumper", "electrical installation",
        "fan", "flameproof apparatus", "foundry", "gas engine", "gasoline engine",
        "haulage", "hydraulic turbine", "loader", "locomotive", "machinery",
        "main fan", "mechanical ventilator", "mineral dressing", "oil engine",
        "pit cage", "pump", "pumping", "rope", "safety lamp", "self-rescuer",
        "shaft", "smithy", "steam turbine", "switchgear", "transformer",
        "ventilation fan", "ventilator", "water wheel", "winder", "winding",
        "workshop",
    },
}


def _keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    lowered = text.lower()
    count = 0
    for keyword in keywords:
        count += len(re.findall(rf"\b{re.escape(keyword.lower())}\b", lowered))
    return count


def risk_level_for_signals(signals: dict[str, int]) -> str:
    if any(count > 3 for count in signals.values()):
        return "high"
    if any(count > 1 for count in signals.values()):
        return "medium"
    if any(count > 0 for count in signals.values()):
        return "low"
    return "none"


def scan_text_for_risk_alert(text: str) -> dict[str, Any]:
    signals = {
        "violations": _keyword_count(text, SAFETY_VIOLATION_KEYWORDS),
        "equipment": _keyword_count(text, EQUIPMENT_FAILURE_KEYWORDS),
        "hazards": _keyword_count(text, HAZARD_KEYWORDS),
    }
    return {
        "risk_signals": signals,
        "risk_level": risk_level_for_signals(signals),
    }

AGENT_MODE_KEYWORDS = {
    "risk_audit": {"risk", "hazard", "unsafe", "danger", "audit", "prevent"},
    "incident_analysis": {"incident", "accident", "fatal", "death", "injury", "cause"},
    "compliance_check": {"rule", "regulation", "compliance", "legal", "must", "notice", "form"},
    "equipment_troubleshooting": {"equipment", "machine", "machinery", "maintenance", "repair", "failure"},
    "document_summary": {"summary", "summarize", "summarise", "brief", "explain document"},
    "safety_training": {"training", "toolbox", "worker", "checklist", "lesson"},
}

ROLE_HINTS = {
    "manager": {"manager", "owner", "agent", "supervisor"},
    "safety_officer": {"safety officer", "officer", "inspector", "compliance"},
    "worker": {"worker", "labour", "operator", "miner"},
    "legal": {"legal", "law", "regulation", "rule", "court", "notice"},
}


@dataclass
class Citation:
    title: str
    excerpt: str
    relevance: float
    page: int | None = None
    section: str | None = None

    def as_source(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "excerpt": self.excerpt[:220],
            "relevance": round(self.relevance, 3),
            "page": self.page,
            "section": self.section,
        }


def document_text(doc: dict[str, Any]) -> str:
    text_path = doc.get("text_path")
    if not text_path:
        return ""
    path = Path(str(text_path))
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def classify_document_type(doc: dict[str, Any], text: str | None = None) -> str:
    stored_type = str(doc.get("type") or "regulation").lower()
    if stored_type == "incident":
        return stored_type

    name = str(doc.get("name") or "").lower()
    readable_text = text if text is not None else document_text(doc)
    sample = readable_text.lower()[:50000]

    if "accident" in name or "incident" in name:
        return "incident"
    accident_table_rows = len(
        re.findall(
            r"\|\s*(?:fire|gas|coal|roof|inundation|blasting|methane|explosion).{0,100}\|\s*\d+\s*fatal",
            sample,
        )
    )
    if accident_table_rows >= 2:
        return "incident"
    dated_entries = len(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", sample))
    marker_count = sum(marker in sample for marker in INCIDENT_MARKERS)
    if dated_entries >= 5 and marker_count >= 4:
        return "incident"

    equipment_signals = extract_document_signals(readable_text).get("equipment", [])
    if stored_type == "regulation" and len(equipment_signals) >= 8 and not any(term in sample for term in ("regulation", "rules", "act")):
        return "manual"

    return stored_type


def detect_agent_mode(question: str) -> str:
    lowered = question.lower()
    scores = {
        mode: sum(1 for keyword in keywords if keyword in lowered)
        for mode, keywords in AGENT_MODE_KEYWORDS.items()
    }
    mode, score = max(scores.items(), key=lambda item: item[1])
    return mode if score else "general"


def detect_user_role(question: str) -> str:
    lowered = question.lower()
    for role, hints in ROLE_HINTS.items():
        if any(hint in lowered for hint in hints):
            return role
    return "general"


def expanded_query_terms(question: str, mode: str) -> list[str]:
    base = {
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if len(token) > 2
    }
    if mode == "incident_analysis":
        base.update(MINE_TERMS["hazards"])
        base.update({"root cause", "corrective action", "notice", "inquiry"})
    elif mode == "compliance_check":
        base.update(MINE_TERMS["actions"])
        base.update({"shall", "required", "regulation", "rule"})
    elif mode == "equipment_troubleshooting":
        base.update(MINE_TERMS["equipment"])
        base.update({"inspection", "maintenance", "failure", "repair"})
    elif mode == "risk_audit":
        base.update(MINE_TERMS["hazards"])
        base.update(MINE_TERMS["actions"])
    elif mode == "safety_training":
        base.update({"training", "precaution", "checklist", "worker", "safe"})
    return sorted(base, key=len, reverse=True)


def _page_hint(lines: list[str], index: int) -> int | None:
    for line in reversed(lines[max(0, index - 40):index + 1]):
        match = re.search(r"\bpage\s*[:\-]?\s*(\d{1,4})\b", line, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _section_hint(lines: list[str], index: int) -> str | None:
    for line in reversed(lines[max(0, index - 20):index + 1]):
        clean = " ".join(line.strip().split())
        if len(clean) < 6 or len(clean) > 140:
            continue
        if re.match(r"^(\d+[A-Z]?\.?|\([a-z0-9]+\)|rule|regulation|section|chapter)\s+", clean, re.I):
            return clean[:120]
        if clean.isupper() and any(char.isalpha() for char in clean):
            return clean.title()[:120]
    return None


def _line_score(line: str, terms: list[str]) -> float:
    lowered = line.lower()
    score = 0.0
    for term in terms:
        if " " in term:
            if term in lowered:
                score += 3.0
        elif re.search(rf"\b{re.escape(term)}\b", lowered):
            score += 1.5
    if any(word in lowered for word in MINE_TERMS["actions"]):
        score += 0.6
    if any(word in lowered for word in MINE_TERMS["hazards"]):
        score += 0.6
    return score


def hybrid_retrieve(
    user_id: str,
    question: str,
    mode: str | None = None,
    limit: int = 8,
    allowed_sources: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected_mode = mode or detect_agent_mode(question)
    terms = expanded_query_terms(question, selected_mode)
    if not terms:
        return []

    results: list[tuple[float, dict[str, Any]]] = []
    for doc in list_documents(user_id):
        title = str(doc.get("name") or "Uploaded document")
        if allowed_sources and title.lower() not in allowed_sources:
            continue
        text = document_text(doc)
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            score = _line_score(line, terms)
            if score <= 0:
                continue
            start = max(0, index - 4)
            end = min(len(lines), index + 7)
            excerpt = " ".join(lines[start:end])
            title_bonus = 2.0 if any(term in title.lower() for term in terms) else 0.0
            density_bonus = min(excerpt.lower().count("shall") * 0.2, 1.0)
            final_score = score + title_bonus + density_bonus
            results.append((final_score, {
                "text": f"Document: {title}\nSection: {_section_hint(lines, index) or 'Relevant passage'}\nPage: {_page_hint(lines, index) or 'unknown'}\n{excerpt[:1800]}",
                "source": title,
                "page": _page_hint(lines, index),
                "section": _section_hint(lines, index),
                "relevance": min(final_score / 12.0, 0.99),
            }))

    deduped: list[tuple[float, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for score, item in sorted(results, key=lambda row: row[0], reverse=True):
        key = (str(item["source"]), str(item["text"])[:180])
        if key in seen:
            continue
        seen.add(key)
        deduped.append((score, item))
        if len(deduped) >= limit:
            break
    return [item for _score, item in deduped]


def citations_from_chunks(chunks: list[dict[str, Any]]) -> list[Citation]:
    citations: list[Citation] = []
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        excerpt = re.sub(r"\s+", " ", text)
        citations.append(Citation(
            title=str(chunk.get("source") or "Uploaded document"),
            excerpt=excerpt,
            relevance=float(chunk.get("relevance") or 0.75),
            page=chunk.get("page") if isinstance(chunk.get("page"), int) else None,
            section=str(chunk.get("section")) if chunk.get("section") else None,
        ))
    return citations


def action_plan_for_mode(mode: str, citations: list[Citation]) -> list[str]:
    has_evidence = bool(citations)
    if mode == "risk_audit":
        return [
            "List the hazards found in the cited material.",
            "Rank each hazard by severity and likelihood.",
            "Assign a control owner and review date.",
        ]
    if mode == "incident_analysis":
        return [
            "Capture immediate facts, injuries, location, equipment, and witnesses.",
            "Preserve the incident site where required by the cited rule.",
            "Map root causes to corrective actions and responsible persons.",
        ]
    if mode == "compliance_check":
        return [
            "Compare the current practice against every cited duty.",
            "Record missing notices, forms, inspections, or approvals.",
            "Close each gap with owner, due date, and evidence.",
        ]
    if mode == "equipment_troubleshooting":
        return [
            "Isolate unsafe equipment before inspection.",
            "Check maintenance history, recurring faults, and operator reports.",
            "Return equipment only after documented corrective action.",
        ]
    if mode == "safety_training":
        return [
            "Turn cited duties into short worker-facing checklist items.",
            "Add one practical example for each hazard.",
            "Confirm understanding with two scenario questions.",
        ]
    return ["Use cited uploaded-document evidence first."] if has_evidence else []


def confidence_notes(citations: list[Citation]) -> str:
    if not citations:
        return "No uploaded-document evidence was found, so this answer should be treated as general guidance."
    strong = sum(1 for citation in citations if citation.relevance >= 0.7)
    return f"Found {len(citations)} uploaded-document evidence passages, including {strong} strong matches."


def build_document_intelligence(user_id: str) -> dict[str, Any]:
    documents = []
    entity_counts: Counter[str] = Counter()
    for doc in list_documents(user_id):
        text = document_text(doc)
        extracted = extract_document_signals(text) if text.strip() else {}
        stored = doc.get("intelligence_signals") or {}
        hazards = sorted(set(extracted.get("hazards") or []) | set(stored.get("hazards") or []))
        actions = sorted(set(extracted.get("actions") or []) | set(stored.get("actions") or []))
        equipment = sorted(set(extracted.get("equipment") or []) | set(stored.get("equipment") or []))
        lowered = text.lower()
        for term in hazards + actions + equipment:
            entity_counts[term] += max(1, lowered.count(term))
        documents.append({
            "id": doc.get("id"),
            "name": doc.get("name"),
            "type": doc.get("type"),
            "status": doc.get("status"),
            "node_count": doc.get("node_count"),
            "signals": {
                "hazards": hazards[:12],
                "actions": actions[:12],
                "equipment": equipment[:12],
            },
            "summary": _summary_from_text(text, str(doc.get("name") or "document")),
        })
    return {
        "documents": documents,
        "top_entities": [
            {"name": name, "count": count}
            for name, count in entity_counts.most_common(15)
        ],
    }


def extract_document_signals(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    return {
        "hazards": sorted(term for term in MINE_TERMS["hazards"] if term in lowered)[:12],
        "actions": sorted(term for term in MINE_TERMS["actions"] if term in lowered)[:12],
        "equipment": sorted(term for term in MINE_TERMS["equipment"] if term in lowered)[:12],
    }


def build_mining_knowledge_graph(user_id: str) -> dict[str, list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    entity_ids: dict[tuple[str, str], str] = {}

    def entity_node(kind: str, label: str) -> str:
        key = (kind, label)
        if key in entity_ids:
            return entity_ids[key]
        node_id = f"{kind}_{len(entity_ids)}"
        entity_ids[key] = node_id
        nodes.append({
            "id": node_id,
            "label": label.title(),
            "type": kind,
            "data": {"full_text": f"{kind.title()} signal: {label}"},
        })
        return node_id

    for doc_index, doc in enumerate(list_documents(user_id)):
        doc_id = f"doc_{doc_index}"
        title = str(doc.get("name") or "Uploaded document")
        text = document_text(doc)
        lowered = text.lower()
        nodes.append({
            "id": doc_id,
            "label": title,
            "type": str(doc.get("type") or "document"),
            "data": {
                "full_text": f"Uploaded document: {title}\nDataset: {doc.get('dataset_name', '')}",
            },
        })

        for kind, terms in (
            ("incident", MINE_TERMS["hazards"]),
            ("equipment", MINE_TERMS["equipment"]),
            ("regulation", MINE_TERMS["actions"]),
        ):
            for term in sorted(terms):
                if term not in lowered:
                    continue
                target = entity_node(kind, term)
                edges.append({
                    "id": f"edge_{doc_id}_{target}",
                    "source": doc_id,
                    "target": target,
                    "label": "mentions",
                })

        if "accident" in lowered or "fatal" in lowered or "death" in lowered:
            for duty in ("notice", "inquiry", "report", "preserve"):
                if duty in lowered:
                    source = entity_node("incident", "accident")
                    target = entity_node("regulation", duty)
                    edges.append({
                        "id": f"edge_{source}_{target}_{doc_index}",
                        "source": source,
                        "target": target,
                        "label": "requires",
                    })

    return {"nodes": nodes, "edges": edges}


def _summary_from_text(text: str, title: str) -> str:
    if not text.strip():
        return f"{title} has no stored readable text."
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    scored: list[tuple[int, str]] = []
    important = MINE_TERMS["hazards"] | MINE_TERMS["actions"] | MINE_TERMS["equipment"]
    for sentence in sentences[:400]:
        lowered = sentence.lower()
        score = sum(1 for term in important if term in lowered)
        if score:
            scored.append((score, sentence[:240]))
    if not scored:
        return sentences[0][:240] if sentences else f"{title} is stored for retrieval."
    return " ".join(sentence for _score, sentence in sorted(scored, reverse=True)[:2])


def risk_signals(user_id: str) -> list[dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "name": "",
        "severity": "medium",
        "count": 0,
        "documents": set(),
        "recommended_action": "",
    })
    severity_terms = {
        "critical": {"fatal", "death", "explosion", "inundation", "collapse"},
        "high": {"fire", "methane", "roof fall", "injury", "blasting"},
    }
    for doc in list_documents(user_id):
        text = document_text(doc).lower()
        for term in MINE_TERMS["hazards"]:
            count = text.count(term)
            if not count:
                continue
            row = signals[term]
            row["name"] = term
            row["count"] += count
            row["documents"].add(str(doc.get("name")))
            if term in severity_terms["critical"]:
                row["severity"] = "critical"
            elif term in severity_terms["high"] and row["severity"] != "critical":
                row["severity"] = "high"
            row["recommended_action"] = _recommended_action(term)
    ordered = sorted(
        signals.values(),
        key=lambda item: ({"critical": 3, "high": 2, "medium": 1}[str(item["severity"])], int(item["count"])),
        reverse=True,
    )
    return [
        {**item, "documents": sorted(item["documents"])[:5]}
        for item in ordered[:12]
    ]


def _recommended_action(term: str) -> str:
    if term in {"fatal", "death", "injury", "accident"}:
        return "Run incident-analysis mode and verify notice, inquiry, and corrective-action duties."
    if term in {"methane", "gas", "ventilation"}:
        return "Review ventilation controls, monitoring records, and emergency withdrawal triggers."
    if term in {"machinery", "haulage", "equipment"}:
        return "Check isolation, guarding, inspection, and maintenance records."
    return "Add this item to the next safety audit and link it to cited regulatory duties."


def user_memory_profile(user_id: str) -> dict[str, Any]:
    docs = list_documents(user_id)
    chats = list_chat_messages(user_id, limit=200)
    intelligence = build_document_intelligence(user_id)
    return {
        "document_count": len(docs),
        "chat_memory_count": len(chats),
        "top_entities": intelligence["top_entities"],
        "risk_signals": risk_signals(user_id),
    }
