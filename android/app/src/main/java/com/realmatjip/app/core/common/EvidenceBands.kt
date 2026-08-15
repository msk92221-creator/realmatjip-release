package com.realmatjip.app.core.common

/** 근거 강도 UI 표시 기준 (스펙 §11) — 표시용이며 Restaurant Score에는 영향 없음. */
enum class EvidenceBand(val label: String) {
    VERY_LOW("낮음"),
    NORMAL("보통"),
    HIGH("높음"),
    VERY_HIGH("매우 높음"),
}

fun evidenceBand(strength: Double): EvidenceBand = when {
    strength >= 0.80 -> EvidenceBand.VERY_HIGH
    strength >= 0.60 -> EvidenceBand.HIGH
    strength >= 0.30 -> EvidenceBand.NORMAL
    else -> EvidenceBand.VERY_LOW
}

fun evidenceLabel(strength: Double): String = evidenceBand(strength).label
