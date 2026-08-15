package com.realmatjip.app.data.restaurant.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ── 목록 ──────────────────────────────────────────────────────

@Serializable
data class RestaurantListResponseDto(
    @SerialName("algorithm_version") val algorithmVersion: String = "",
    val count: Int = 0,
    val items: List<RestaurantListItemDto> = emptyList(),
)

@Serializable
data class RestaurantListItemDto(
    val id: String,
    val name: String,
    val category: String = "",
    val lat: Double = 0.0,
    val lng: Double = 0.0,
    @SerialName("overall_a") val overallA: Double? = null,
    @SerialName("overall_b") val overallB: Double? = null,
    @SerialName("n_raw") val nRaw: Int = 0,
    @SerialName("n_eff") val nEff: Double = 0.0,
    @SerialName("evidence_strength") val evidenceStrength: Double = 0.0,
    @SerialName("evidence_label") val evidenceLabel: String = "",
    @SerialName("local_badge") val localBadge: Boolean = false,
    @SerialName("manipulation_score") val manipulationScore: Double = 0.0,
)

// ── 상세 ──────────────────────────────────────────────────────

@Serializable
data class RestaurantDetailResponseDto(
    val id: String,
    val name: String,
    val category: String = "",
    val lat: Double = 0.0,
    val lng: Double = 0.0,
    val address: String = "",
    val scores: ScoresDto? = null,
    val detail: DetailPayloadDto? = null,
    val message: String? = null,
)

@Serializable
data class ScoresDto(
    @SerialName("overall_a") val overallA: Double? = null,
    @SerialName("overall_b") val overallB: Double? = null,
)

@Serializable
data class DetailPayloadDto(
    val subscores: SubScoresDto,
    val signals: SignalsDto,
    val explanation: List<ExplanationItemDto> = emptyList(),
    val platforms: List<PlatformStatDto> = emptyList(),
    @SerialName("calculated_at") val calculatedAt: String? = null,
)

@Serializable
data class SubScoresDto(
    @SerialName("rating_adjusted") val ratingAdjusted: Double = 0.0,
    val local: Double = 0.0,
    val trust: Double = 0.0,
    @SerialName("ad_free") val adFree: Double = 0.0,
    val food: Double? = null,
    val value: Double? = null,
    val repeat: Double = 0.0,
)

@Serializable
data class SignalsDto(
    val consistency: Double = 0.0,
    val longevity: Double = 0.0,
    @SerialName("manipulation_score") val manipulationScore: Double = 0.0,
    @SerialName("dup_count") val dupCount: Int = 0,
    @SerialName("n_raw") val nRaw: Int = 0,
    @SerialName("n_eff") val nEff: Double = 0.0,
    @SerialName("local_evidence") val localEvidence: Double = 0.0,
    @SerialName("evidence_strength") val evidenceStrength: Double = 0.0,
    @SerialName("evidence_label") val evidenceLabel: String = "",
    @SerialName("local_badge") val localBadge: Boolean = false,
)

@Serializable
data class ExplanationItemDto(
    val term: String = "",
    val label: String = "",
    val value: Double = 0.0,
    val points: Double = 0.0,
)

@Serializable
data class PlatformStatDto(
    val source: String = "",
    @SerialName("n_reviews") val nReviews: Int = 0,
    @SerialName("sum_w") val sumW: Double = 0.0,
    @SerialName("shrunk_rating") val shrunkRating: Double = 0.0,
)

// ── 리뷰 ──────────────────────────────────────────────────────

@Serializable
data class ReviewsResponseDto(
    @SerialName("restaurant_id") val restaurantId: String = "",
    @SerialName("ad_filter") val adFilter: String = "basic",
    val threshold: Double? = null,
    val total: Int = 0,
    val returned: Int = 0,
    val items: List<ReviewDto> = emptyList(),
)

@Serializable
data class ReviewDto(
    val id: String,
    val source: String = "",
    val rating: Double? = null,
    val text: String = "",
    @SerialName("reviewed_at") val reviewedAt: String = "",
    @SerialName("duplicate_of") val duplicateOf: String? = null,
    val analysis: ReviewAnalysisDto? = null,
    @SerialName("manual_label") val manualLabel: String? = null,
)

@Serializable
data class ReviewAnalysisDto(
    val analyzer: String = "",
    @SerialName("ad_probability") val adProbability: Double = 0.0,
    @SerialName("ad_confidence") val adConfidence: Double = 0.0,
    val authenticity: Double = 0.0,
    val specificity: Double = 0.0,
    @SerialName("local_probability") val localProbability: Double = 0.0,
    @SerialName("repeat_visit") val repeatVisit: Boolean? = null,
    @SerialName("negative_points") val negativePoints: Boolean? = null,
    @SerialName("pseudo_rating") val pseudoRating: Double? = null,
    val summary: String? = null,
)

// ── 라벨 ──────────────────────────────────────────────────────

@Serializable
data class LabelRequestDto(
    val label: String? = null,
    val note: String = "",
)

@Serializable
data class LabelResponseDto(
    @SerialName("review_id") val reviewId: String = "",
    val label: String? = null,
)

// ── 메타/잡/통계 ──────────────────────────────────────────────

@Serializable
data class MetaDto(
    @SerialName("algorithm_version") val algorithmVersion: String = "",
    val analyzer: String? = null,
    @SerialName("prompt_version") val promptVersion: String? = null,
    @SerialName("schema_version") val schemaVersion: String? = null,
    @SerialName("ad_filter_levels") val adFilterLevels: Map<String, Double> = emptyMap(),
    @SerialName("auth_required") val authRequired: Boolean = false,
)

@Serializable
data class JobDto(
    val id: Int = 0,
    val kind: String = "",
    val status: String = "",
    val progress: kotlinx.serialization.json.JsonObject? = null,
    val error: String? = null,
)

@Serializable
data class RecalculateResponseDto(
    @SerialName("job_id") val jobId: Int = 0,
    val kind: String = "",
    @SerialName("algorithm_version") val algorithmVersion: String = "",
)

@Serializable
data class StatsDto(
    val restaurants: Int = 0,
    val reviews: Int = 0,
    val analyzed: Int = 0,
    val unanalyzed: Int = 0,
    @SerialName("duplicate_flagged") val duplicateFlagged: Int = 0,
    @SerialName("manual_labels") val manualLabels: Map<String, Int> = emptyMap(),
    @SerialName("reviews_by_source") val reviewsBySource: Map<String, Int> = emptyMap(),
    @SerialName("latest_score") val latestScore: LatestScoreDto? = null,
)

@Serializable
data class LatestScoreDto(
    @SerialName("algorithm_version") val algorithmVersion: String = "",
    @SerialName("batch_id") val batchId: String = "",
    @SerialName("calculated_at") val calculatedAt: String = "",
)

@Serializable
data class SeedResponseDto(
    val seeded: SeedSummaryDto = SeedSummaryDto(),
    val reset: Boolean = false,
)

@Serializable
data class SeedSummaryDto(
    val restaurants: Int = 0,
    val reviews: Int = 0,
)

@Serializable
data class HealthDto(
    val status: String = "",
    val version: String = "",
)
