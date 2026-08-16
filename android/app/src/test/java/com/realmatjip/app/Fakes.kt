package com.realmatjip.app

import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.BackendStats
import com.realmatjip.app.domain.model.Favorite
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.domain.model.RecentRestaurant
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewsPage
import com.realmatjip.app.domain.repository.AdminRepository
import com.realmatjip.app.domain.repository.FavoriteRepository
import com.realmatjip.app.domain.repository.RecentRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import com.realmatjip.app.data.update.DownloadEvent
import com.realmatjip.app.data.update.UpdateRepository
import com.realmatjip.app.data.update.UpdateState
import com.realmatjip.app.core.network.ApiError
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map

fun testRestaurant(
    id: String = "rest-b",
    name: String = "을지면옥",
    overallA: Double? = 76.6,
    localBadge: Boolean = true,
) = Restaurant(
    id = id, name = name, category = "평양냉면", lat = 37.56, lng = 126.99,
    overallA = overallA, overallB = overallA?.minus(2.6), nRaw = 34, nEff = 20.5,
    evidenceStrength = 0.72, localBadge = localBadge, manipulationScore = 0.04,
)

fun testDetail(
    id: String = "rest-b",
    name: String = "을지면옥",
    overallA: Double? = 76.6,
) = RestaurantDetail(
    id = id, name = name, category = "평양냉면", address = "서울 중구 을지로",
    lat = 37.56, lng = 126.99, overallA = overallA, overallB = overallA?.minus(2.6),
    subscores = null, signals = null, explanation = emptyList(), platforms = emptyList(),
    calculatedAt = "2026-08-15T12:00:00",
)

class FakeRestaurantRepository : RestaurantRepository {
    var restaurants: List<Restaurant> = emptyList()
    var detailResponse: RestaurantDetail = testDetail()
    var reviewsResponse: ReviewsPage = ReviewsPage("rest-b", AdFilter.BASIC, 0.7, 60, 50, emptyList())
    var searchError: ApiError? = null
    var detailError: ApiError? = null
    var labels = mutableMapOf<String, String?>()
    val searchCalls = mutableListOf<Map<String, String?>>()

    override suspend fun search(
        query: String?, localOnly: Boolean, minOverall: Double?, sort: String, bbox: String?, limit: Int,
    ): ApiResult<List<Restaurant>> {
        searchCalls.add(
            mapOf(
                "q" to query, "local_only" to localOnly.toString(),
                "min_overall" to minOverall?.toString(), "sort" to sort, "bbox" to bbox,
            )
        )
        searchError?.let { return ApiResult.Failure(it) }
        return ApiResult.Success(restaurants)
    }

    override suspend fun detail(id: String): ApiResult<RestaurantDetail> {
        detailError?.let { return ApiResult.Failure(it) }
        return ApiResult.Success(detailResponse)
    }

    override suspend fun reviews(id: String, filter: AdFilter, limit: Int): ApiResult<ReviewsPage> {
        return ApiResult.Success(reviewsResponse.copy(restaurantId = id, adFilter = filter))
    }

    override suspend fun setLabel(reviewId: String, label: String?): ApiResult<Unit> {
        labels[reviewId] = label
        return ApiResult.Success(Unit)
    }

    override suspend fun meta() = ApiResult.Success(
        com.realmatjip.app.domain.model.BackendMeta(
            algorithmVersion = "v0.1-phase0", analyzer = "mock-v1", promptVersion = "mock-1",
            schemaVersion = "1", adFilterLevels = mapOf("basic" to 0.7), authRequired = false,
        )
    )

    override suspend fun testConnection(): ApiResult<String> = ApiResult.Success("ok · v0.1-phase0")
}

/** 재계산 잡을 순차 상태로 반환: queued → running → done. */
class FakeAdminRepository : AdminRepository {
    val jobScript = mutableListOf("queued", "running", "done")
    var jobCallCount = 0
    var recalculateCalls = 0
    var backup: String = "{\"restaurants\": 5}"

    override suspend fun recalculate(): ApiResult<Int> {
        recalculateCalls++
        jobCallCount = 0
        return ApiResult.Success(recalculateCalls)
    }

    override suspend fun job(jobId: Int): ApiResult<JobInfo> {
        val status = jobScript.getOrNull(jobCallCount) ?: "done"
        jobCallCount++
        return ApiResult.Success(
            JobInfo(id = jobId, kind = "recalculate", status = status, error = null,
                    done = if (status == "done") 5 else 2, total = 5)
        )
    }

    override suspend fun stats(): ApiResult<BackendStats> = ApiResult.Success(
        BackendStats(5, 175, 175, 0, 11, emptyMap(), emptyMap(), "2026-08-15", "v0.1-phase0")
    )

    override suspend fun seed(reset: Boolean): ApiResult<String> = ApiResult.Success("식당 5개 / 리뷰 175개")

    override suspend fun backupExport(): ApiResult<String> = ApiResult.Success(backup)

    var importPreviewResult: ApiResult<com.realmatjip.app.domain.model.ImportPreview> =
        ApiResult.Success(
            com.realmatjip.app.domain.model.ImportPreview(
                total = 3, valid = 2, invalid = 1, exactDuplicates = 0,
                estimatedNewReviews = 2, newRestaurants = 1, matchedRestaurants = 0,
                errors = listOf(com.realmatjip.app.domain.model.ImportRowError(3, "source", "플랫폼 누락")),
            )
        )
    var importCommitResult: ApiResult<com.realmatjip.app.domain.model.ImportCommit> =
        ApiResult.Success(
            com.realmatjip.app.domain.model.ImportCommit(
                insertedRestaurants = 1, insertedReviews = 2, skippedDuplicates = 0, invalid = 1,
                errors = emptyList(),
            )
        )
    var analyzeEstimateResult: ApiResult<com.realmatjip.app.domain.model.AnalyzeEstimate> =
        ApiResult.Success(
            com.realmatjip.app.domain.model.AnalyzeEstimate(
                analyzer = "mock-rules-v1", promptVersion = "review-analysis-v1",
                pendingTotal = 2, toAnalyze = 2, cachedHits = 0,
                estimatedTokensInput = 4000, estimatedTokensOutput = 700,
                estimatedCost = 0.004, withinLimits = true, reviewsExceedCap = false,
            )
        )
    var analyzePendingCalls = 0

    override suspend fun importPreview(format: String, content: String) = importPreviewResult
    override suspend fun importCommit(format: String, content: String) = importCommitResult

    override suspend fun analyzeEstimate() = analyzeEstimateResult

    override suspend fun analyzePending(): ApiResult<Int> {
        analyzePendingCalls++
        return ApiResult.Success(100 + analyzePendingCalls)
    }
}

class FakeFavoriteRepository : FavoriteRepository {
    private val _favorites = MutableStateFlow<List<Favorite>>(emptyList())
    override val favorites: StateFlow<List<Favorite>> = _favorites.asStateFlow()
    val added = mutableListOf<String>()

    override fun isFavorite(restaurantId: String): Flow<Boolean> =
        _favorites.map { list -> list.any { it.id == restaurantId } }

    override suspend fun add(restaurantId: String, name: String, category: String, score: Double?) {
        added += restaurantId
        _favorites.value = _favorites.value + Favorite(restaurantId, name, category, score, 0L)
    }

    override suspend fun remove(restaurantId: String) {
        _favorites.value = _favorites.value.filterNot { it.id == restaurantId }
    }
}

class FakeRecentRepository : RecentRepository {
    private val _recents = MutableStateFlow<List<RecentRestaurant>>(emptyList())
    override val recents: StateFlow<List<RecentRestaurant>> = _recents.asStateFlow()
    val recorded = mutableListOf<String>()

    override suspend fun record(restaurantId: String, name: String, category: String, score: Double?) {
        recorded += restaurantId
        _recents.value = listOf(RecentRestaurant(restaurantId, name, category, score, 0L)) + _recents.value
    }
}

class FakeAppSettings(
    override val backendUrl: Flow<String> = MutableStateFlow("http://10.0.2.2:8000"),
    override val apiToken: Flow<String> = MutableStateFlow(""),
    override val defaultAdFilter: Flow<AdFilter> = MutableStateFlow(AdFilter.BASIC),
    override val developerMode: Flow<Boolean> = MutableStateFlow(false),
    override val homeRegionLabel: Flow<String> = MutableStateFlow(""),
    override val homeRegionLat: Flow<Float> = MutableStateFlow(0f),
    override val homeRegionLng: Flow<Float> = MutableStateFlow(0f),
) : AppSettings {
    var savedLabel: String = ""
    var savedLat: Double = 0.0
    var savedLng: Double = 0.0

    override suspend fun setBackendUrl(url: String) = Unit
    override suspend fun setApiToken(token: String) = Unit
    override suspend fun setDefaultAdFilter(filter: AdFilter) = Unit
    override suspend fun setDeveloperMode(enabled: Boolean) = Unit
    override suspend fun setHomeRegion(label: String, lat: Double, lng: Double) {
        savedLabel = label; savedLat = lat; savedLng = lng
    }
}

class FakeProviderRepository : com.realmatjip.app.domain.repository.ProviderRepository {
    var searchResult: com.realmatjip.app.core.network.ApiResult<List<com.realmatjip.app.domain.model.GooglePlace>> =
        com.realmatjip.app.core.network.ApiResult.Success(emptyList())
    var previewResult: com.realmatjip.app.core.network.ApiResult<com.realmatjip.app.domain.model.GoogleImportPreview> =
        com.realmatjip.app.core.network.ApiResult.Success(
            com.realmatjip.app.domain.model.GoogleImportPreview(
                place = com.realmatjip.app.domain.model.GooglePlace(
                    placeId = "test", name = "테스트", formattedAddress = "",
                    lat = 0.0, lng = 0.0, primaryType = "", rating = 4.5,
                    userRatingCount = 100, googleMapsUrl = "",
                ),
                match = com.realmatjip.app.domain.model.GoogleMatch(
                    matchType = "no_match", matchedRestaurantId = null,
                    matchedName = "", distanceM = null, confidence = 0.0,
                ),
                reviewCount = 3, newReviews = 3, duplicates = 0, existingReviews = 0,
                reviewSamples = emptyList(),
            )
        )
    var commitResult: com.realmatjip.app.core.network.ApiResult<com.realmatjip.app.domain.model.GoogleImportCommit> =
        com.realmatjip.app.core.network.ApiResult.Success(
            com.realmatjip.app.domain.model.GoogleImportCommit(
                restaurantId = "gp-test", restaurantName = "테스트", action = "created",
                insertedReviews = 3, skippedDuplicates = 0, reviewSamplesTotal = 3,
                googleRating = 4.5, googleRatingCount = 100,
            )
        )
    val searchCalls = mutableListOf<String>()

    override suspend fun search(query: String, lat: Double?, lng: Double?) = searchResult
    override suspend fun importPreview(placeId: String, forceNew: Boolean) = previewResult
    override suspend fun importCommit(placeId: String, forceNew: Boolean) = commitResult
}


/** Phase 4 테스트용 — 항상 업데이트 없음. */
class FakeUpdateRepository : UpdateRepository {
    override suspend fun checkForUpdate(force: Boolean): UpdateState = UpdateState.UpToDate
    override fun downloadApk(update: UpdateState.Available): kotlinx.coroutines.flow.Flow<DownloadEvent> =
        kotlinx.coroutines.flow.flowOf(DownloadEvent.Failed("테스트 미구현"))
}
