package com.realmatjip.app.data.admin.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ImportPreviewDto(
    val total: Int = 0,
    val valid: Int = 0,
    val invalid: Int = 0,
    @SerialName("exact_duplicates") val exactDuplicates: Int = 0,
    @SerialName("estimated_new_reviews") val estimatedNewReviews: Int = 0,
    @SerialName("new_restaurants") val newRestaurants: Int = 0,
    @SerialName("matched_restaurants") val matchedRestaurants: Int = 0,
    val errors: List<ImportErrorDto> = emptyList(),
)

@Serializable
data class ImportErrorDto(
    val row: Int = 0,
    val field: String = "",
    val reason: String = "",
)

@Serializable
data class ImportCommitDto(
    @SerialName("inserted_restaurants") val insertedRestaurants: Int = 0,
    @SerialName("inserted_reviews") val insertedReviews: Int = 0,
    @SerialName("skipped_duplicates") val skippedDuplicates: Int = 0,
    val invalid: Int = 0,
    val errors: List<ImportErrorDto> = emptyList(),
)

@Serializable
data class AnalyzeEstimateDto(
    val analyzer: String = "",
    @SerialName("prompt_version") val promptVersion: String = "",
    @SerialName("pending_total") val pendingTotal: Int = 0,
    @SerialName("to_analyze") val toAnalyze: Int = 0,
    @SerialName("cached_hits") val cachedHits: Int = 0,
    @SerialName("estimated_tokens_input") val estimatedTokensInput: Long = 0,
    @SerialName("estimated_tokens_output") val estimatedTokensOutput: Long = 0,
    @SerialName("estimated_cost") val estimatedCost: Double = 0.0,
    @SerialName("within_limits") val withinLimits: Boolean = true,
    @SerialName("reviews_exceed_cap") val reviewsExceedCap: Boolean = false,
)
