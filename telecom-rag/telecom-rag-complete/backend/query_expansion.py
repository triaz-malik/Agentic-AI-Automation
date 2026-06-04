"""
query_expansion.py — Step 3
============================
582-term telecom query expansion across 15 topics.
Drop into: C:\\Working\\Telecom RAG\\telecom-rag-complete\\backend\\

Usage in retriever:
    from query_expansion import expand_query
    expanded = expand_query("VoNR call drop")
    # → original query + domain-specific synonym terms appended
"""

from __future__ import annotations
import re
from typing import Dict, List, Set

# ─────────────────────────────────────────────────────────────────────────────
# EXPANSION DICTIONARY — 15 topics, ~40 terms each
# ─────────────────────────────────────────────────────────────────────────────

EXPANSION_TERMS: Dict[str, List[str]] = {

    # ── 1. VoNR / Voice over NR ──────────────────────────────────────────────
    "vonr": [
        "VoNR", "Voice over NR", "VoiceOverNR", "IMS voice", "5G voice",
        "VonrCallDropRate", "VonrAirTimeoutEpsfbTimer", "VonrHoTimer",
        "N.CallDrop.CU.VoNR", "5QI1", "5QI 1", "QCI1", "GBR bearer",
        "IMS PDU session", "Ps5qiCfg", "VoNRAlgoSwitch", "VonrEpsFallback",
        "EPS fallback", "EPSFB", "VonrSrvccSwitch", "SRVCC",
        "IMS registration", "SIP session", "VoLTE migration",
        "NR voice", "native voice 5G", "VonrCoverage",
        "VonrQosSwitch", "VonrPsHoSwitch", "UL voice packet",
        "voice bearer", "VoNR admission", "VonrPsCell",
        "VonrSwitchAlgo", "voice RLF", "VoNR timer",
        "T301 VoNR", "VonrRetryTimer", "VonrMaxRetry",
        "IMS APN", "P-CSCF", "SBC voice", "AMR codec",
    ],

    # ── 2. Call Drop ──────────────────────────────────────────────────────────
    "call_drop": [
        "call drop", "CallDrop", "call release", "abnormal release",
        "N.CallDrop", "N.CallDrop.CU", "N.CallDrop.DU",
        "radio link failure", "RLF", "T310", "N310", "N311",
        "T311", "re-establishment failure", "ReestabFail",
        "PDCP discard", "PDCP SN wraparound", "T-Reordering",
        "handover failure", "HOFail", "T304 expiry",
        "RACH failure", "contention resolution failure",
        "beam failure", "BFD", "beam failure detection",
        "beam failure recovery", "BFR", "call drop rate",
        "CDR", "drop cause", "RRC release abnormal",
        "MaxRetxThreshold", "RLC max retransmission",
        "PDCP integrity failure", "security failure",
        "NAS reject", "MM reject", "connection failure",
        "air interface timeout", "RRC connection lost",
    ],

    # ── 3. Handover ───────────────────────────────────────────────────────────
    "handover": [
        "handover", "HO", "handoff", "mobility", "A3 event", "A5 event",
        "A1 event", "A2 event", "B1 event", "B2 event",
        "HoA3Offset", "HoA3Hyst", "HoA3TimeToTrig", "TimeToTrigger",
        "Hysteresis", "CellIndividualOffset", "CIO",
        "HoPrepTimer", "HoExecTimer", "T304", "MeasGapConfig",
        "HoMaxRetx", "HoFailRate", "handover success rate",
        "N.HO.ExecSuccOut", "N.HO.PrepSuccOut",
        "intra-frequency HO", "inter-frequency HO",
        "inter-RAT HO", "Xn handover", "NG handover",
        "conditional handover", "CHO", "DAPS handover",
        "MRO", "mobility robustness optimisation",
        "HoTriggerSwitch", "HoAlgoSwitch", "MLB handover",
        "load-based handover", "coverage handover",
        "too early HO", "too late HO", "ping-pong HO",
    ],

    # ── 4. EN-DC / NSA ────────────────────────────────────────────────────────
    "endc": [
        "EN-DC", "ENDC", "NSA", "non-standalone", "dual connectivity",
        "NR secondary cell group", "SCG", "MCG", "SCG failure",
        "SCG addition", "SCG change", "B1 threshold",
        "NrScgFailure", "EndcAlgoSwitch", "EndcHoSwitch",
        "EndcSplitBearerSwitch", "split bearer",
        "X2 interface", "SgNB", "MgNB", "secondary gNB",
        "master gNB", "NR anchor", "LTE anchor",
        "LTE 5G coexistence", "EUTRA NR DC",
        "EndcScgFailTimer", "NR SCG RLF",
        "EndcCovThreshold", "EndcActSwitch",
        "SCG bearer", "MCG bearer", "split bearer ratio",
        "EN-DC setup", "EN-DC release", "EN-DC modification",
        "N.ENDC.EstabSucc", "N.ENDC.RelAbnorm",
    ],

    # ── 5. Carrier Aggregation ────────────────────────────────────────────────
    "carrier_aggregation": [
        "carrier aggregation", "CA", "SCell", "PCell", "PSCell",
        "secondary cell", "primary cell", "SCell addition",
        "SCell activation", "SCell deactivation",
        "CaAlgoSwitch", "CaActSwitch", "CaThreshold",
        "inter-band CA", "intra-band CA", "UL CA", "DL CA",
        "component carrier", "CC", "bandwidth combination",
        "NR CA", "LTE CA", "5G CA",
        "CaTimerActive", "CaTimerDeactive",
        "N.CA.SCellAddSucc", "N.CA.SCellActSucc",
        "CA measurement", "RSRP threshold CA",
        "CellCaSwitch", "CaMaxSCell",
        "aggregated bandwidth", "total throughput CA",
        "cross-carrier scheduling", "CA PDCCH",
    ],

    # ── 6. MIMO / Beamforming ─────────────────────────────────────────────────
    "mimo": [
        "MIMO", "massive MIMO", "mMIMO", "beamforming", "beam management",
        "beam sweeping", "beam measurement", "beam reporting",
        "SSB beam", "CSI-RS beam", "P1 procedure", "P2 procedure",
        "P3 procedure", "TCI state", "beam failure",
        "NrMimoAlgoSwitch", "MimoLayerNum", "RankIndicator",
        "RI", "CQI", "PMI", "codebook", "SRS",
        "uplink MIMO", "DL MIMO", "4T4R", "8T8R", "64T64R",
        "antenna port", "spatial multiplexing",
        "transmit diversity", "open loop MIMO",
        "closed loop MIMO", "MU-MIMO", "SU-MIMO",
        "beamforming weight", "digital beamforming",
        "analog beamforming", "hybrid beamforming",
        "NrMimoSwitch", "MimoRiThreshold",
    ],

    # ── 7. MLB / Load Balancing ───────────────────────────────────────────────
    "mlb": [
        "MLB", "mobility load balancing", "load balancing",
        "cell load", "PRB utilization", "load threshold",
        "MlbAlgoSwitch", "MlbSwitch", "NRCellQciBearer",
        "MlbHoA3Offset", "MlbLoadThreshold",
        "MlbA3Offset", "MlbTimeToTrig",
        "UL load", "DL load", "resource utilization",
        "N.PRB.DL.Used", "N.PRB.UL.Used",
        "overload", "congestion", "cell congestion",
        "load report", "X2 load report",
        "HoTriggerByLoad", "load-based offset",
        "MLB inter-frequency", "MLB intra-frequency",
        "MlbRsrpThreshold", "MlbMinOffset",
        "SON load balancing", "automatic load balance",
        "traffic steering", "load steering",
    ],

    # ── 8. PDCP ───────────────────────────────────────────────────────────────
    "pdcp": [
        "PDCP", "Packet Data Convergence Protocol",
        "PDCP discard timer", "DiscardTimer", "T-Reordering",
        "PDCP SN", "sequence number", "PDCP status report",
        "header compression", "ROHC", "integrity protection",
        "ciphering", "PDCP reestablishment",
        "PDCP data recovery", "PDCP duplication",
        "split bearer PDCP", "UL data split",
        "PdcpDiscardTimer", "PdcpSnSize",
        "PDCP PDU", "PDCP SDU", "PDCP control",
        "out-of-order delivery", "in-order delivery",
        "PDCP window", "PDCP COUNT",
        "NR PDCP", "LTE PDCP", "PDCP layer",
        "drb-ContinueROHC", "PDCP config",
        "N.PDCP.PacketDiscard", "PDCP loss",
    ],

    # ── 9. PRB / Resource Management ─────────────────────────────────────────
    "prb": [
        "PRB", "Physical Resource Block", "resource block",
        "PRB utilization", "PRB usage", "scheduling",
        "UL PRB", "DL PRB", "PRB allocation",
        "N.PRB.DL.Used", "N.PRB.UL.Used",
        "N.PRB.DL.Avail", "N.PRB.UL.Avail",
        "resource utilization ratio", "RUR",
        "scheduler", "round robin", "proportional fair",
        "PF scheduler", "GBR scheduler", "non-GBR",
        "resource reservation", "SRS resource",
        "PUCCH resource", "PUSCH resource",
        "frequency resource", "time resource",
        "slot", "mini-slot", "subframe",
        "numerology", "SCS", "subcarrier spacing",
        "bandwidth part", "BWP", "active BWP",
    ],

    # ── 10. QoS / Bearer ─────────────────────────────────────────────────────
    "qos": [
        "QoS", "quality of service", "5QI", "QCI", "bearer",
        "GBR", "non-GBR", "AMBR", "MBR", "GFBR", "MFBR",
        "ARP", "allocation and retention priority",
        "QoS flow", "DRB", "data radio bearer",
        "PDU session", "QoS mapping", "DRB mapping",
        "QosFlowToBeSetup", "QosProfileList",
        "5QI 1", "5QI 2", "5QI 3", "5QI 4", "5QI 5",
        "5QI 65", "5QI 69", "5QI 70", "5QI 79", "5QI 80",
        "packet delay budget", "PDB", "packet error rate", "PER",
        "priority level", "preemption", "reflective QoS",
        "DSCP marking", "QoS enforcement", "UPF QoS",
        "N.QosFlow.AddSucc", "QosFlowSwitch",
    ],

    # ── 11. DRX ───────────────────────────────────────────────────────────────
    "drx": [
        "DRX", "discontinuous reception", "sleep mode",
        "onDurationTimer", "drx-InactivityTimer",
        "drx-RetransmissionTimerDL", "drx-RetransmissionTimerUL",
        "shortDRX-Cycle", "longDRX-Cycle", "drxStartOffset",
        "DRX cycle", "DRX slot", "DRX wake",
        "C-DRX", "connected mode DRX", "I-DRX",
        "DRX group", "DRX config", "DrxAlgoSwitch",
        "DrxLongCycle", "DrxShortCycle", "DrxInactTimer",
        "power saving", "UE power", "sleep cycle",
        "DRX HARQ", "DRX scheduling request",
        "N.DRX.UE", "DRX adoption rate",
        "eDRX", "extended DRX", "DRX throughput impact",
        "DrxSwitch", "DrxQciConfig",
    ],

    # ── 12. Coverage / RSRP ───────────────────────────────────────────────────
    "coverage": [
        "coverage", "RSRP", "RSRQ", "SINR", "signal quality",
        "reference signal received power",
        "CoverageAlgoSwitch", "CovHoThreshold",
        "A2 threshold", "A2Threshold", "WeakCovThreshold",
        "cell edge", "coverage hole", "pilot pollution",
        "downlink coverage", "uplink coverage",
        "CoverageHoSwitch", "AntennaDownTilt",
        "transmit power", "P0", "alpha", "pathloss",
        "RSRP threshold", "coverage measurement",
        "SSB RSRP", "CSI-RS RSRP", "L3 filter",
        "filterCoefficient", "A3 RSRP",
        "N.RSRP.Avg", "N.Coverage.Weak",
        "poor coverage UE", "coverage optimization",
    ],

    # ── 13. Interference ─────────────────────────────────────────────────────
    "interference": [
        "interference", "SINR degradation", "inter-cell interference",
        "interference coordination", "ICIC", "eICIC", "feICIC",
        "ABS", "almost blank subframe", "cell interference",
        "UL interference", "DL interference", "noise rise",
        "IOT", "interference over thermal",
        "InterferenceSwitch", "InterferAlgoSwitch",
        "CoMP", "coordinated multipoint",
        "IRC", "interference rejection combining",
        "MRC", "maximum ratio combining",
        "NAICS", "network assisted interference cancellation",
        "pilot interference", "frequency reuse",
        "fractional frequency reuse", "FFR",
        "power control", "OLPC", "CLPC",
        "N.UL.Interference", "interference KPI",
        "neighbor interference", "cross-slot interference",
    ],

    # ── 14. Throughput ────────────────────────────────────────────────────────
    "throughput": [
        "throughput", "DL throughput", "UL throughput",
        "cell throughput", "user throughput", "peak rate",
        "average throughput", "N.User.DL.Thp", "N.User.UL.Thp",
        "N.Cell.DL.Thp", "N.Cell.UL.Thp",
        "PDCP throughput", "MAC throughput",
        "spectral efficiency", "bits per Hz",
        "MCS", "modulation", "64QAM", "256QAM", "QPSK",
        "BLER", "block error rate", "target BLER",
        "CQI threshold", "MCS table", "TB size",
        "transport block", "HARQ retransmission",
        "throughput degradation", "low throughput UE",
        "ThroughputAlgoSwitch", "MaxMcsSwitch",
        "N.PRB.DL.Thp", "resource efficiency",
    ],

    # ── 15. Network Slicing ───────────────────────────────────────────────────
    "slicing": [
        "network slicing", "slice", "NSSAI", "S-NSSAI",
        "slice selection", "NSSF", "slice isolation",
        "slice QoS", "slice SLA", "slice capacity",
        "SliceAlgoSwitch", "SliceQosSwitch",
        "NrSliceConfig", "SlicePriorityConfig",
        "RAN slicing", "transport slicing", "core slicing",
        "slice scheduler", "slice PRB", "slice bandwidth",
        "slice admission", "slice handover",
        "SST", "slice service type", "SD", "slice differentiator",
        "eMBB slice", "URLLC slice", "mMTC slice",
        "N.Slice.DL.Thp", "N.Slice.UL.Thp",
        "slice KPI", "slice monitoring",
        "NSSI", "network slice subnet instance",
        "slice SLA assurance", "closed-loop slice",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# TRIGGER KEYWORDS — maps query keywords → expansion topic
# ─────────────────────────────────────────────────────────────────────────────

TOPIC_TRIGGERS: Dict[str, str] = {
    # VoNR
    "vonr": "vonr", "voice over nr": "vonr", "ims voice": "vonr",
    "epsfb": "vonr", "eps fallback": "vonr", "srvcc": "vonr",
    "vonrcalldroprate": "vonr", "vonrairtimeout": "vonr",

    # Call Drop
    "call drop": "call_drop", "calldrop": "call_drop",
    "rlf": "call_drop", "radio link failure": "call_drop",
    "t310": "call_drop", "n310": "call_drop", "t311": "call_drop",
    "re-establishment": "call_drop", "reestab": "call_drop",
    "beam failure": "call_drop", "bfr": "call_drop",

    # Handover
    "handover": "handover", "ho ": "handover", " ho": "handover",
    "handoff": "handover", "a3 event": "handover",
    "t304": "handover", "mro": "handover",
    "conditional handover": "handover", "cho": "handover",

    # EN-DC
    "en-dc": "endc", "endc": "endc", "nsa": "endc",
    "dual connectivity": "endc", "scg": "endc",
    "secondary cell group": "endc", "sgnb": "endc",

    # CA
    "carrier aggregation": "carrier_aggregation",
    "scell": "carrier_aggregation", "pcell": "carrier_aggregation",
    " ca ": "carrier_aggregation", "component carrier": "carrier_aggregation",

    # MIMO
    "mimo": "mimo", "beamforming": "mimo", "beam management": "mimo",
    "massive mimo": "mimo", "mmimo": "mimo",
    "beam failure": "mimo", "tci state": "mimo",

    # MLB
    "mlb": "mlb", "load balancing": "mlb", "load balance": "mlb",
    "mlbalgoswitchswitch": "mlb", "cell load": "mlb",
    "prb utilization": "mlb",

    # PDCP
    "pdcp": "pdcp", "discard timer": "pdcp",
    "t-reordering": "pdcp", "header compression": "pdcp",
    "rohc": "pdcp",

    # PRB
    "prb": "prb", "resource block": "prb",
    "prb usage": "prb", "scheduler": "prb",
    "scheduling": "prb",

    # QoS
    "qos": "qos", "5qi": "qos", "qci": "qos",
    "bearer": "qos", "gbr": "qos", "ambr": "qos",
    "pdu session": "qos",

    # DRX
    "drx": "drx", "discontinuous reception": "drx",
    "sleep mode": "drx", "drx cycle": "drx",
    "power saving": "drx",

    # Coverage
    "coverage": "coverage", "rsrp": "coverage",
    "rsrq": "coverage", "sinr": "coverage",
    "cell edge": "coverage", "weak coverage": "coverage",

    # Interference
    "interference": "interference", "icic": "interference",
    "comp": "interference", "sinr degradation": "interference",
    "noise rise": "interference",

    # Throughput
    "throughput": "throughput", "dl thp": "throughput",
    "ul thp": "throughput", "mcs": "throughput",
    "bler": "throughput", "spectral efficiency": "throughput",

    # Slicing
    "slice": "slicing", "slicing": "slicing",
    "nssai": "slicing", "s-nssai": "slicing",
    "network slice": "slicing", "ran slice": "slicing",
}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def _detect_topics(query: str) -> Set[str]:
    """Detect which expansion topics are relevant to this query."""
    q_lower = query.lower()
    matched: Set[str] = set()
    for trigger, topic in TOPIC_TRIGGERS.items():
        if trigger in q_lower:
            matched.add(topic)
    return matched


def expand_query(query: str, max_terms: int = 40) -> str:
    """
    Expand a telecom query with domain-specific synonym terms.

    Returns the original query with relevant expansion terms appended.
    The expanded string is used for BM25 and vector search — NOT shown to user.

    Args:
        query:      Original user query string
        max_terms:  Max expansion terms to append (default 40)

    Returns:
        Expanded query string
    """
    topics = _detect_topics(query)
    if not topics:
        return query  # No expansion needed — return as-is

    expansion_set: List[str] = []
    seen: Set[str] = set()

    for topic in sorted(topics):  # sorted for determinism
        terms = EXPANSION_TERMS.get(topic, [])
        for term in terms:
            if term not in seen and term.lower() not in query.lower():
                expansion_set.append(term)
                seen.add(term)
            if len(expansion_set) >= max_terms:
                break
        if len(expansion_set) >= max_terms:
            break

    if not expansion_set:
        return query

    expanded = query + " " + " ".join(expansion_set)
    return expanded


def get_expansion_terms(query: str) -> List[str]:
    """Return just the expansion terms for a query (used for logging/debug)."""
    topics = _detect_topics(query)
    terms: List[str] = []
    seen: Set[str] = set()
    for topic in sorted(topics):
        for term in EXPANSION_TERMS.get(topic, []):
            if term not in seen:
                terms.append(term)
                seen.add(term)
    return terms


def count_terms() -> int:
    """Return total number of expansion terms across all topics."""
    return sum(len(v) for v in EXPANSION_TERMS.values())


# ─────────────────────────────────────────────────────────────────────────────
# CLI test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Total expansion terms: {count_terms()}")
    print()
    test_queries = [
        "VoNR call drop reasons and timers",
        "MLB parameter NRCellQciBearer MlbAlgoSwitch",
        "PDCP discard timer VoNR packet loss",
        "handover failure T304 expiry",
        "PRB utilization threshold",
        "what is 5G network slicing NSSAI",
    ]
    for q in test_queries:
        topics = _detect_topics(q)
        terms = get_expansion_terms(q)
        print(f"Query: {q}")
        print(f"  Topics: {topics}")
        print(f"  Terms added: {len(terms)} → {terms[:8]}...")
        print()
