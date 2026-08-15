package com.realmatjip.app.domain.model

/** 광고 가능성 필터 (스펙 §12/§26) — 기본 0.7 / 엄격 0.4 / 매우 엄격 0.2 */
enum class AdFilter(val queryValue: String, val label: String) {
    OFF("off", "전체"),
    BASIC("basic", "기본"),
    STRICT("strict", "엄격"),
    VERY_STRICT("very_strict", "매우 엄격");

    companion object {
        fun fromName(name: String?): AdFilter? = entries.firstOrNull { it.name == name }
        fun fromQuery(value: String?): AdFilter? = entries.firstOrNull { it.queryValue == value }
    }
}

/** 목록 아이템 — GET /api/restaurants items */
data class Restaurant(
    val id: String,
    val name: String,
    val category: String,
    val lat: Double,
    val lng: Double,
    val overallA: Double?,
    val overallB: Double?,
    val nRaw: Int,
    val nEff: Double,
    val evidenceStrength: Double,
    val localBadge: Boolean,
    val manipulationScore: Double,
) {
    val primaryScore: Double? get() = overallA ?: overallB
}

data class SubScores(
    val ratingAdjusted: Double,
    val local: Double,
    val trust: Double,
    val adFree: Double,
    val food: Double?,
    val value: Double?,
    val repeat: Double,
)

data class DetailSignals(
    val consistency: Double,
    val longevity: Double,
    val manipulationScore: Double,
    val dupCount: Int,
    val nRaw: Int,
    val nEff: Double,
    val localEvidence: Double,
    val evidenceStrength: Double,
    val localBadge: Boolean,
)

data class ExplanationItem(
    val term: String,
    val label: String,
    val value: Double,
    val points: Double,
)

data class PlatformStat(
    val source: String,
    val nReviews: Int,
    val sumW: Double,
    val shrunkRating: Double,
)

/** 상세 — GET /api/restaurants/{id} */
data class RestaurantDetail(
    val id: String,
    val name: String,
    val category: String,
    val address: String,
    val lat: Double,
    val lng: Double,
    val overallA: Double?,
    val overallB: Double?,
    val subscores: SubScores?,
    val signals: DetailSignals?,
    val explanation: List<ExplanationItem>,
    val platforms: List<PlatformStat>,
    val calculatedAt: String?,
    val message: String? = null,
    val fromCache: Boolean = false,
    val cacheAgeHours: Long? = null,
) {
    val primaryScore: Double? get() = overallA ?: overallB
}

data class ReviewAnalysisSummary(
    val analyzer: String,
    val adProbability: Double,
    val adConfidence: Double,
    val authenticity: Double,
    val specificity: Double,
    val localProbability: Double,
    val repeatVisit: Boolean?,
    val negativePoints: Boolean?,
    val pseudoRating: Double?,
    val summary: String?,
)

data class ReviewItem(
    val id: String,
    val source: String,
    val rating: Double?,
    val text: String,
    val reviewedAt: String,
    val duplicateOf: String?,
    val analysis: ReviewAnalysisSummary?,
    val manualLabel: String?,
)

data class ReviewsPage(
    val restaurantId: String,
    val adFilter: AdFilter,
    val threshold: Double?,
    val total: Int,
    val returned: Int,
    val items: List<ReviewItem>,
)

data class BackendMeta(
    val algorithmVersion: String,
    val analyzer: String?,
    val promptVersion: String?,
    val schemaVersion: String?,
    val adFilterLevels: Map<String, Double>,
    val authRequired: Boolean,
)

data class JobInfo(
    val id: Int,
    val kind: String,
    val status: String,
    val error: String?,
    val done: Int? = null,
    val total: Int? = null,
    // LLM 분석 잡(progress 확장) — 재계산 잡에서는 null
    val completed: Int? = null,
    val cached: Int? = null,
    val failed: Int? = null,
    val tokensInput: Long? = null,
    val tokensOutput: Long? = null,
    val estimatedCost: Double? = null,
    val analyzer: String? = null,
    val model: String? = null,
    val promptVersion: String? = null,
) {
    val isFinished: Boolean get() = status == "done" || status == "failed"
}

data class BackendStats(
    val restaurants: Int,
    val reviews: Int,
    val analyzed: Int,
    val unanalyzed: Int,
    val duplicateFlagged: Int,
    val manualLabels: Map<String, Int>,
    val reviewsBySource: Map<String, Int>,
    val latestScoreCalculatedAt: String?,
    val algorithmVersion: String?,
)

data class Favorite(
    val id: String,
    val name: String,
    val category: String,
    val overallScoreSnapshot: Double?,
    val savedAt: Long,
)

data class RecentRestaurant(
    val id: String,
    val name: String,
    val category: String,
    val overallScoreSnapshot: Double?,
    val viewedAt: Long,
)

// ── Import / LLM 분석 (Phase 3A) ─────────────────────────────

data class ImportRowError(val row: Int, val field: String, val reason: String)

data class ImportPreview(
    val total: Int,
    val valid: Int,
    val invalid: Int,
    val exactDuplicates: Int,
    val estimatedNewReviews: Int,
    val newRestaurants: Int,
    val matchedRestaurants: Int,
    val errors: List<ImportRowError>,
)

data class ImportCommit(
    val insertedRestaurants: Int,
    val insertedReviews: Int,
    val skippedDuplicates: Int,
    val invalid: Int,
    val errors: List<ImportRowError>,
)

data class AnalyzeEstimate(
    val analyzer: String,
    val promptVersion: String,
    val pendingTotal: Int,
    val toAnalyze: Int,
    val cachedHits: Int,
    val estimatedTokensInput: Long,
    val estimatedTokensOutput: Long,
    val estimatedCost: Double,
    val withinLimits: Boolean,
    val reviewsExceedCap: Boolean,
)

// ── Google Places Provider (Phase 3B) ────────────────────────

data class GooglePlace(
    val placeId: String,
    val name: String,
    val formattedAddress: String,
    val lat: Double,
    val lng: Double,
    val primaryType: String,
    val rating: Double?,
    val userRatingCount: Int,
    val googleMapsUrl: String,
)

data class GoogleMatch(
    val matchType: String,          // exact_place_id | name_coords | name_address | no_match
    val matchedRestaurantId: String?,
    val matchedName: String,
    val distanceM: Double?,
    val confidence: Double,
)

data class GoogleReviewSample(
    val rating: Double?,
    val text: String,
    val authorName: String,
)

data class GoogleImportPreview(
    val place: GooglePlace,
    val match: GoogleMatch,
    val reviewCount: Int,
    val newReviews: Int,
    val duplicates: Int,
    val existingReviews: Int,
    val reviewSamples: List<GoogleReviewSample>,
)

data class GoogleImportCommit(
    val restaurantId: String,
    val restaurantName: String,
    val action: String,             // created | linked | skipped
    val insertedReviews: Int,
    val skippedDuplicates: Int,
    val reviewSamplesTotal: Int,
    val googleRating: Double?,
    val googleRatingCount: Int,
)
