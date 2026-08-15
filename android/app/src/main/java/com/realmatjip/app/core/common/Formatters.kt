package com.realmatjip.app.core.common

import java.util.Locale
import kotlin.math.roundToInt

/** presentation 전용 포맷 — 도메인 값은 그대로 두고 표시 형태만 만든다 (스펙 §4). */
object Formatters {

    /** 76.63 → "76.6", null → "-" */
    fun score(value: Double?): String =
        if (value == null) "-" else String.format(Locale.ROOT, "%.1f", value)

    /** 76.63 → "77" (마커/배지용 정수) */
    fun scoreInt(value: Double?): String =
        if (value == null) "-" else value.roundToInt().toString()

    /** 0.08 → "8%", 0.755 → "76%" */
    fun percent(ratio: Double?): String =
        if (ratio == null) "-" else "${(ratio * 100).roundToInt()}%"

    /** 하위 점수(0~1) → 0~100 정수 */
    fun subScore(ratio: Double?): String =
        if (ratio == null) "-" else (ratio * 100).roundToInt().toString()

    /** 4.0 → "★★★★" */
    fun stars(rating: Double?): String {
        if (rating == null) return "별점 없음"
        val full = rating.roundToInt().coerceIn(0, 5)
        return "★".repeat(full) + "☆".repeat(5 - full)
    }

    /** n_eff 20.5 → "20.5" */
    fun effReviews(nEff: Double): String = String.format(Locale.ROOT, "%.1f", nEff)
}
