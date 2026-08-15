package com.realmatjip.app.data.providers

import com.realmatjip.app.core.network.ApiClient
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.apiCall
import com.realmatjip.app.data.providers.dto.GoogleImportCommitDto
import com.realmatjip.app.data.providers.dto.GoogleImportPreviewDto
import com.realmatjip.app.data.providers.dto.GoogleSearchResponseDto
import com.realmatjip.app.domain.model.GoogleImportCommit
import com.realmatjip.app.domain.model.GoogleImportPreview
import com.realmatjip.app.domain.model.GoogleMatch
import com.realmatjip.app.domain.model.GooglePlace
import com.realmatjip.app.domain.model.GoogleReviewSample
import com.realmatjip.app.domain.repository.ProviderRepository
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import javax.inject.Inject
import javax.inject.Singleton

interface ProviderApi {

    @GET("/api/providers/google/search")
    suspend fun search(
        @Query("q") query: String,
        @Query("lat") lat: Double? = null,
        @Query("lng") lng: Double? = null,
        @Query("radius") radius: Int? = null,
        @Query("limit") limit: Int? = null,
    ): GoogleSearchResponseDto

    @POST("/api/providers/google/import/preview")
    suspend fun importPreview(@Body body: ImportPreviewBody): GoogleImportPreviewDto

    @POST("/api/providers/google/import/commit")
    suspend fun importCommit(@Body body: ImportPreviewBody): GoogleImportCommitDto
}

@kotlinx.serialization.Serializable
data class ImportPreviewBody(
    val place_id: String,
    val force_new: Boolean = false,
)

@Singleton
class ProviderRepositoryImpl @Inject constructor(
    private val apiClient: ApiClient,
) : ProviderRepository {

    private fun api(): ProviderApi = apiClient.service(ProviderApi::class)

    override suspend fun search(query: String, lat: Double?, lng: Double?): ApiResult<List<GooglePlace>> =
        apiCall {
            api().search(query, lat, lng).results.map { it.toDomain() }
        }

    override suspend fun importPreview(placeId: String, forceNew: Boolean): ApiResult<GoogleImportPreview> =
        apiCall {
            api().importPreview(ImportPreviewBody(placeId, forceNew)).toDomain()
        }

    override suspend fun importCommit(placeId: String, forceNew: Boolean): ApiResult<GoogleImportCommit> =
        apiCall {
            api().importCommit(ImportPreviewBody(placeId, forceNew)).toDomain()
        }
}

// ── DTO → Domain 매핑 ────────────────────────────────────────

private fun com.realmatjip.app.data.providers.dto.GooglePlaceDto.toDomain() = GooglePlace(
    placeId = placeId, name = name, formattedAddress = formattedAddress,
    lat = lat, lng = lng, primaryType = primaryType,
    rating = rating, userRatingCount = userRatingCount, googleMapsUrl = googleMapsUrl,
)

private fun GoogleImportPreviewDto.toDomain() = GoogleImportPreview(
    place = restaurant.toDomain(),
    match = GoogleMatch(
        matchType = match.matchType,
        matchedRestaurantId = match.matchedRestaurantId,
        matchedName = match.matchedName,
        distanceM = match.distanceM,
        confidence = match.confidence,
    ),
    reviewCount = reviewCount,
    newReviews = newReviews,
    duplicates = duplicates,
    existingReviews = existingReviews,
    reviewSamples = reviewSamples.map {
        GoogleReviewSample(rating = it.rating, text = it.text, authorName = it.authorName)
    },
)

private fun GoogleImportCommitDto.toDomain() = GoogleImportCommit(
    restaurantId = restaurantId,
    restaurantName = restaurantName,
    action = action,
    insertedReviews = insertedReviews,
    skippedDuplicates = skippedDuplicates,
    reviewSamplesTotal = reviewSamplesTotal,
    googleRating = googleRating,
    googleRatingCount = googleRatingCount,
)
