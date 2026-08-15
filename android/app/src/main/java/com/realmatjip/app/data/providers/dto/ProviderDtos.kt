package com.realmatjip.app.data.providers.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ── Google Places 검색 결과 ──────────────────────────────────

@Serializable
data class GoogleSearchResponseDto(
    val query: String = "",
    val count: Int = 0,
    val results: List<GooglePlaceDto> = emptyList(),
)

@Serializable
data class GooglePlaceDto(
    val provider: String = "google_places",
    @SerialName("place_id") val placeId: String = "",
    val name: String = "",
    @SerialName("formatted_address") val formattedAddress: String = "",
    val lat: Double = 0.0,
    val lng: Double = 0.0,
    @SerialName("primary_type") val primaryType: String = "",
    val rating: Double? = null,
    @SerialName("user_rating_count") val userRatingCount: Int = 0,
    @SerialName("google_maps_url") val googleMapsUrl: String = "",
)

// ── Import Preview ───────────────────────────────────────────

@Serializable
data class GoogleImportPreviewDto(
    val restaurant: GooglePlaceDto = GooglePlaceDto(),
    val match: GoogleMatchDto = GoogleMatchDto(),
    @SerialName("review_count") val reviewCount: Int = 0,
    @SerialName("new_reviews") val newReviews: Int = 0,
    val duplicates: Int = 0,
    @SerialName("existing_reviews") val existingReviews: Int = 0,
    @SerialName("review_samples") val reviewSamples: List<GoogleReviewSampleDto> = emptyList(),
)

@Serializable
data class GoogleMatchDto(
    @SerialName("match_type") val matchType: String = "no_match",
    @SerialName("matched_restaurant_id") val matchedRestaurantId: String? = null,
    @SerialName("matched_name") val matchedName: String = "",
    @SerialName("distance_m") val distanceM: Double? = null,
    val confidence: Double = 0.0,
)

@Serializable
data class GoogleReviewSampleDto(
    val rating: Double? = null,
    val text: String = "",
    @SerialName("author_name") val authorName: String = "",
)

// ── Import Commit ────────────────────────────────────────────

@Serializable
data class GoogleImportCommitDto(
    @SerialName("restaurant_id") val restaurantId: String = "",
    @SerialName("restaurant_name") val restaurantName: String = "",
    val action: String = "",  // created | linked | skipped
    @SerialName("inserted_reviews") val insertedReviews: Int = 0,
    @SerialName("skipped_duplicates") val skippedDuplicates: Int = 0,
    @SerialName("review_samples_total") val reviewSamplesTotal: Int = 0,
    @SerialName("google_rating") val googleRating: Double? = null,
    @SerialName("google_rating_count") val googleRatingCount: Int = 0,
)
