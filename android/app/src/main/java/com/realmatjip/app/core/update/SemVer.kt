package com.realmatjip.app.core.update

/**
 * SemVer 2.0.0 파서/비교기 — 업데이트 버전 비교의 단일 기준 (스펙 §10).
 *
 * 앱 버전 예: "0.2.0-phase2", 릴리즈 태그 예: "v0.3.0".
 * - 선행 "v" 무시, major.minor.patch 필수 (누락 시 0 처리)
 * - pre-release("phase2" 등)는 같은 버전의 정식 릴리스보다 낮다 (SemVer 규칙 11)
 * - 비교 대상에 parse 불가능한 값이 오면 [IllegalArgumentException]
 */
data class SemVer(
    val major: Int,
    val minor: Int,
    val patch: Int,
    val preRelease: List<String> = emptyList(),
) : Comparable<SemVer> {

    companion object {
        fun parse(raw: String): SemVer {
            val trimmed = raw.trim().removePrefix("v").removePrefix("V")
            val coreAndPre = trimmed.split("-", limit = 2)
            val numbers = coreAndPre[0].split(".")
            if (numbers.size > 3) throw IllegalArgumentException("버전 세그먼트 초과: $raw")
            val ints = numbers.map { segment ->
                segment.toIntOrNull() ?: throw IllegalArgumentException("버전이 아님: $raw")
            }
            return SemVer(
                major = ints.getOrElse(0) { 0 },
                minor = ints.getOrElse(1) { 0 },
                patch = ints.getOrElse(2) { 0 },
                preRelease = coreAndPre.getOrNull(1)
                    ?.split(".")?.filter { it.isNotBlank() } ?: emptyList(),
            )
        }

        /** 설정 값(minimumVersion 등) 파싱 — 빈 값은 null, 잘못된 값도 null (설정을 신뢰하지 않고 무시). */
        fun parseOrNull(raw: String?): SemVer? =
            raw?.takeIf { it.isNotBlank() }?.let { runCatching { parse(it) }.getOrNull() }
    }

    val isPreRelease: Boolean get() = preRelease.isNotEmpty()

    override fun compareTo(other: SemVer): Int {
        (major.compareTo(other.major)).takeIf { it != 0 }?.let { return it }
        (minor.compareTo(other.minor)).takeIf { it != 0 }?.let { return it }
        (patch.compareTo(other.patch)).takeIf { it != 0 }?.let { return it }
        // SemVer 규칙 11: pre-release 없음 > pre-release 있음
        if (preRelease.isEmpty() && other.preRelease.isEmpty()) return 0
        if (preRelease.isEmpty()) return 1
        if (other.preRelease.isEmpty()) return -1
        val size = minOf(preRelease.size, other.preRelease.size)
        for (i in 0 until size) {
            val a = preRelease[i]
            val b = other.preRelease[i]
            val aNum = a.toIntOrNull()
            val bNum = b.toIntOrNull()
            val cmp = when {
                aNum != null && bNum != null -> aNum.compareTo(bNum)
                aNum != null -> -1 // 숫자 < 영숫자
                bNum != null -> 1
                else -> a.compareTo(b)
            }
            if (cmp != 0) return cmp
        }
        return preRelease.size.compareTo(other.preRelease.size)
    }

    override fun toString(): String =
        "$major.$minor.$patch" + if (preRelease.isEmpty()) "" else "-" + preRelease.joinToString(".")
}
