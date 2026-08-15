package com.realmatjip.app.core.common

import com.realmatjip.app.domain.model.AdFilter
import org.junit.Assert.assertEquals
import org.junit.Test

class AdFilterTest {

    @Test
    fun `쿼리값 매핑 - 기본 0_7 엄격 0_4 매우엄격 0_2`() {
        assertEquals("off", AdFilter.OFF.queryValue)
        assertEquals("basic", AdFilter.BASIC.queryValue)
        assertEquals("strict", AdFilter.STRICT.queryValue)
        assertEquals("very_strict", AdFilter.VERY_STRICT.queryValue)
    }

    @Test
    fun `fromQuery 복원`() {
        assertEquals(AdFilter.BASIC, AdFilter.fromQuery("basic"))
        assertEquals(AdFilter.VERY_STRICT, AdFilter.fromQuery("very_strict"))
        assertEquals(null, AdFilter.fromQuery("unknown"))
        assertEquals(null, AdFilter.fromQuery(null))
    }

    @Test
    fun `fromName 복원`() {
        assertEquals(AdFilter.STRICT, AdFilter.fromName("STRICT"))
        assertEquals(null, AdFilter.fromName("nope"))
    }

    @Test
    fun `표시 라벨`() {
        assertEquals("전체", AdFilter.OFF.label)
        assertEquals("매우 엄격", AdFilter.VERY_STRICT.label)
    }
}

class EvidenceBandTest {

    @Test
    fun `4단계 밴드 - 스펙 §11 임계값`() {
        assertEquals(EvidenceBand.VERY_LOW, evidenceBand(0.00))
        assertEquals(EvidenceBand.VERY_LOW, evidenceBand(0.29))
        assertEquals(EvidenceBand.NORMAL, evidenceBand(0.30))
        assertEquals(EvidenceBand.NORMAL, evidenceBand(0.59))
        assertEquals(EvidenceBand.HIGH, evidenceBand(0.60))
        assertEquals(EvidenceBand.HIGH, evidenceBand(0.79))
        assertEquals(EvidenceBand.VERY_HIGH, evidenceBand(0.80))
        assertEquals(EvidenceBand.VERY_HIGH, evidenceBand(1.00))
    }

    @Test
    fun `라벨 문자열`() {
        assertEquals("낮음", evidenceLabel(0.1))
        assertEquals("보통", evidenceLabel(0.45))
        assertEquals("높음", evidenceLabel(0.65))
        assertEquals("매우 높음", evidenceLabel(0.9))
    }
}

class FormattersTest {

    @Test
    fun `점수 포맷`() {
        assertEquals("76.6", Formatters.score(76.63))
        assertEquals("100.0", Formatters.score(100.0))
        assertEquals("-", Formatters.score(null))
    }

    @Test
    fun `마커용 정수 점수`() {
        assertEquals("77", Formatters.scoreInt(76.6))
        assertEquals("-", Formatters.scoreInt(null))
    }

    @Test
    fun `퍼센트 포맷`() {
        assertEquals("8%", Formatters.percent(0.08))
        assertEquals("76%", Formatters.percent(0.755))
        assertEquals("-", Formatters.percent(null))
    }

    @Test
    fun `하위 점수 0_1을 0_100으로`() {
        assertEquals("82", Formatters.subScore(0.823))
        assertEquals("-", Formatters.subScore(null))
    }

    @Test
    fun `별점 렌더링`() {
        assertEquals("★★★★☆", Formatters.stars(4.0))
        assertEquals("★★★★★", Formatters.stars(4.6))
        assertEquals("별점 없음", Formatters.stars(null))
    }

    @Test
    fun `유효 리뷰`() {
        assertEquals("20.5", Formatters.effReviews(20.52))
    }
}
