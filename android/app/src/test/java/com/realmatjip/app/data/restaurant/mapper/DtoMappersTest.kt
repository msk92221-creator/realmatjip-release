package com.realmatjip.app.data.restaurant.mapper

import com.realmatjip.app.data.restaurant.dto.RestaurantDetailResponseDto
import com.realmatjip.app.data.restaurant.dto.RestaurantListItemDto
import com.realmatjip.app.data.restaurant.dto.ReviewDto
import com.realmatjip.app.data.restaurant.dto.ReviewsResponseDto
import com.realmatjip.app.domain.model.AdFilter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DtoMappersTest {

    @Test
    fun `목록 DTO를 도메인으로`() {
        val dto = RestaurantListItemDto(
            id = "rest-d", name = "충무노포국밥", category = "돼지국밥",
            lat = 37.56, lng = 127.01, overallA = 78.8, overallB = 76.2,
            nRaw = 16, nEff = 6.9, evidenceStrength = 0.46,
            localBadge = true, manipulationScore = 0.0,
        )
        val domain = dto.toDomain()
        assertEquals("rest-d", domain.id)
        assertEquals(78.8, domain.overallA!!, 1e-9)
        assertEquals(78.8, domain.primaryScore!!, 1e-9)
        assertTrue(domain.localBadge)
    }

    @Test
    fun `점수 없는 목록 항목은 primaryScore가 null`() {
        val dto = RestaurantListItemDto(id = "x", name = "미계산식당")
        assertNull(dto.toDomain().primaryScore)
    }

    @Test
    fun `상세 DTO - 점수 없음 케이스`() {
        val dto = RestaurantDetailResponseDto(
            id = "rest-b", name = "을지면옥", message = "점수 없음 — 재계산을 실행하세요",
        )
        val domain = dto.toDomain()
        assertNull(domain.overallA)
        assertNull(domain.subscores)
        assertTrue(domain.explanation.isEmpty())
        assertFalse(domain.fromCache)
        assertEquals("점수 없음 — 재계산을 실행하세요", domain.message)
    }

    @Test
    fun `상세 DTO - 전체 필드와 캐시 플래그`() {
        val dto = RestaurantDetailResponseDto(
            id = "rest-b", name = "을지면옥", address = "을지로",
            scores = com.realmatjip.app.data.restaurant.dto.ScoresDto(overallA = 76.6, overallB = 74.0),
            detail = com.realmatjip.app.data.restaurant.dto.DetailPayloadDto(
                subscores = com.realmatjip.app.data.restaurant.dto.SubScoresDto(
                    ratingAdjusted = 0.882, local = 0.565, trust = 0.776, adFree = 0.811,
                    food = 0.76, value = 0.67, repeat = 0.258,
                ),
                signals = com.realmatjip.app.data.restaurant.dto.SignalsDto(
                    consistency = 0.95, longevity = 0.32, manipulationScore = 0.0,
                    dupCount = 0, nRaw = 34, nEff = 20.5, localEvidence = 13.3,
                    evidenceStrength = 0.72, localBadge = true,
                ),
                explanation = listOf(
                    com.realmatjip.app.data.restaurant.dto.ExplanationItemDto(
                        term = "rating", label = "가중 보정 평점", value = 0.882, points = 48.5,
                    )
                ),
                platforms = listOf(
                    com.realmatjip.app.data.restaurant.dto.PlatformStatDto(
                        source = "naver_map", nReviews = 12, sumW = 7.5, shrunkRating = 0.88,
                    )
                ),
                calculatedAt = "2026-08-15T01:57:58",
            ),
        )
        val domain = dto.toDomain(fromCache = true, cacheAgeHours = 30)
        assertEquals(76.6, domain.overallA!!, 1e-9)
        assertEquals(0.565, domain.subscores!!.local, 1e-9)
        assertEquals(20.5, domain.signals!!.nEff, 1e-9)
        assertEquals("가중 보정 평점", domain.explanation.first().label)
        assertEquals("naver_map", domain.platforms.first().source)
        assertTrue(domain.fromCache)
        assertEquals(30L, domain.cacheAgeHours)
    }

    @Test
    fun `리뷰 DTO - 분석 없는 리뷰와 수동 라벨`() {
        val dto = ReviewsResponseDto(
            restaurantId = "rest-a", adFilter = "very_strict", threshold = 0.2,
            total = 60, returned = 10,
            items = listOf(
                ReviewDto(id = "r-1", text = "맛있어요", reviewedAt = "2026-08-01",
                          manualLabel = "normal"),
                ReviewDto(
                    id = "r-2", text = "광고성", reviewedAt = "2026-08-01", rating = 5.0,
                    analysis = com.realmatjip.app.data.restaurant.dto.ReviewAnalysisDto(
                        analyzer = "mock-v1", adProbability = 0.85, adConfidence = 0.8,
                        authenticity = 0.3, specificity = 0.5, localProbability = 0.1,
                        repeatVisit = false, negativePoints = null, pseudoRating = null,
                        summary = "프로모션성 패턴",
                    ),
                ),
            ),
        )
        val page = dto.toDomain()
        assertEquals(AdFilter.VERY_STRICT, page.adFilter)
        assertEquals(0.2, page.threshold!!, 1e-9)
        assertNull(page.items[0].analysis)
        assertEquals("normal", page.items[0].manualLabel)
        assertEquals(0.85, page.items[1].analysis!!.adProbability, 1e-9)
        assertEquals(false, page.items[1].analysis!!.repeatVisit)
    }
}
