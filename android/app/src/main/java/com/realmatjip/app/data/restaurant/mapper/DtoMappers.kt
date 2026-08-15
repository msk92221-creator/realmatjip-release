package com.realmatjip.app.data.restaurant.mapper

import com.realmatjip.app.data.restaurant.dto.RestaurantDetailResponseDto
import com.realmatjip.app.data.restaurant.dto.RestaurantListItemDto
import com.realmatjip.app.data.restaurant.dto.ReviewDto
import com.realmatjip.app.data.restaurant.dto.ReviewsResponseDto
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.DetailSignals
import com.realmatjip.app.domain.model.ExplanationItem
import com.realmatjip.app.domain.model.PlatformStat
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewAnalysisSummary
import com.realmatjip.app.domain.model.ReviewItem
import com.realmatjip.app.domain.model.ReviewsPage
import com.realmatjip.app.domain.model.SubScores
import com.realmatjip.app.data.restaurant.dto.MetaDto

/** Network DTO → Domain 변환 (스펙 §4). UI는 DTO를 직접 모른다. */

fun RestaurantListItemDto.toDomain(): Restaurant = Restaurant(
    id = id,
    name = name,
    category = category,
    lat = lat,
    lng = lng,
    overallA = overallA,
    overallB = overallB,
    nRaw = nRaw,
    nEff = nEff,
    evidenceStrength = evidenceStrength,
    localBadge = localBadge,
    manipulationScore = manipulationScore,
)

fun RestaurantDetailResponseDto.toDomain(
    fromCache: Boolean = false,
    cacheAgeHours: Long? = null,
): RestaurantDetail = RestaurantDetail(
    id = id,
    name = name,
    category = category,
    address = address,
    lat = lat,
    lng = lng,
    overallA = scores?.overallA,
    overallB = scores?.overallB,
    subscores = detail?.subscores?.let {
        SubScores(
            ratingAdjusted = it.ratingAdjusted,
            local = it.local,
            trust = it.trust,
            adFree = it.adFree,
            food = it.food,
            value = it.value,
            repeat = it.repeat,
        )
    },
    signals = detail?.signals?.let {
        DetailSignals(
            consistency = it.consistency,
            longevity = it.longevity,
            manipulationScore = it.manipulationScore,
            dupCount = it.dupCount,
            nRaw = it.nRaw,
            nEff = it.nEff,
            localEvidence = it.localEvidence,
            evidenceStrength = it.evidenceStrength,
            localBadge = it.localBadge,
        )
    },
    explanation = detail?.explanation?.map {
        ExplanationItem(term = it.term, label = it.label, value = it.value, points = it.points)
    } ?: emptyList(),
    platforms = detail?.platforms?.map {
        PlatformStat(source = it.source, nReviews = it.nReviews, sumW = it.sumW, shrunkRating = it.shrunkRating)
    } ?: emptyList(),
    calculatedAt = detail?.calculatedAt,
    message = message,
    fromCache = fromCache,
    cacheAgeHours = cacheAgeHours,
)

fun ReviewDto.toDomain(): ReviewItem = ReviewItem(
    id = id,
    source = source,
    rating = rating,
    text = text,
    reviewedAt = reviewedAt,
    duplicateOf = duplicateOf,
    analysis = analysis?.let {
        ReviewAnalysisSummary(
            analyzer = it.analyzer,
            adProbability = it.adProbability,
            adConfidence = it.adConfidence,
            authenticity = it.authenticity,
            specificity = it.specificity,
            localProbability = it.localProbability,
            repeatVisit = it.repeatVisit,
            negativePoints = it.negativePoints,
            pseudoRating = it.pseudoRating,
            summary = it.summary,
        )
    },
    manualLabel = manualLabel,
)

fun ReviewsResponseDto.toDomain(): ReviewsPage = ReviewsPage(
    restaurantId = restaurantId,
    adFilter = AdFilter.fromQuery(adFilter) ?: AdFilter.BASIC,
    threshold = threshold,
    total = total,
    returned = returned,
    items = items.map { it.toDomain() },
)

fun MetaDto.toDomain(): BackendMeta = BackendMeta(
    algorithmVersion = algorithmVersion,
    analyzer = analyzer,
    promptVersion = promptVersion,
    schemaVersion = schemaVersion,
    adFilterLevels = adFilterLevels,
    authRequired = authRequired,
)
