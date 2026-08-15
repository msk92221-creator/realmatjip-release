package com.realmatjip.app.domain.repository

import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.AnalyzeEstimate
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.BackendStats
import com.realmatjip.app.domain.model.Favorite
import com.realmatjip.app.domain.model.ImportCommit
import com.realmatjip.app.domain.model.ImportPreview
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewsPage
import kotlinx.coroutines.flow.Flow

interface RestaurantRepository {
    suspend fun search(
        query: String? = null,
        localOnly: Boolean = false,
        minOverall: Double? = null,
        sort: String = "overall_a",
        bbox: String? = null,
        limit: Int = 50,
    ): ApiResult<List<Restaurant>>

    /** 네트워크 우선, 실패 시 Room 캐시 폴백 (fromCache=true). */
    suspend fun detail(id: String): ApiResult<RestaurantDetail>

    suspend fun reviews(id: String, filter: AdFilter, limit: Int = 100): ApiResult<ReviewsPage>

    /** 수동 라벨 저장/해제 — 사람의 판단이 LLM보다 우선한다. */
    suspend fun setLabel(reviewId: String, label: String?): ApiResult<Unit>

    suspend fun meta(): ApiResult<BackendMeta>

    /** 연결 테스트(/health) — 성공 시 버전 문자열 반환. */
    suspend fun testConnection(): ApiResult<String>
}

interface AdminRepository {
    /** 점수 재계산 잡 시작 — 성공 시 jobId. LLM 재호출 없음. */
    suspend fun recalculate(): ApiResult<Int>

    suspend fun job(jobId: Int): ApiResult<JobInfo>

    suspend fun stats(): ApiResult<BackendStats>

    suspend fun seed(reset: Boolean = false): ApiResult<String>

    /** 전체 백업 덤프(JSON 문자열). */
    suspend fun backupExport(): ApiResult<String>

    /** Import dry run — DB 변경 없음 (스펙 §2). */
    suspend fun importPreview(format: String, content: String): ApiResult<ImportPreview>

    /** Import 실제 반영. */
    suspend fun importCommit(format: String, content: String): ApiResult<ImportCommit>

    /** 분석 dry run — 대상/캐시/예상 사용량 (스펙 §6). */
    suspend fun analyzeEstimate(): ApiResult<AnalyzeEstimate>

    /** 미분석 리뷰 LLM 분석 잡 시작 — 성공 시 jobId. */
    suspend fun analyzePending(): ApiResult<Int>
}

interface FavoriteRepository {
    val favorites: Flow<List<Favorite>>
    fun isFavorite(restaurantId: String): Flow<Boolean>
    suspend fun add(restaurantId: String, name: String, category: String, score: Double?)
    suspend fun remove(restaurantId: String)
}

interface RecentRepository {
    val recents: Flow<List<com.realmatjip.app.domain.model.RecentRestaurant>>
    suspend fun record(restaurantId: String, name: String, category: String, score: Double?)
}

interface ProviderRepository {
    /** Google Places 텍스트 검색 (스펙 §3). */
    suspend fun search(query: String, lat: Double? = null, lng: Double? = null): ApiResult<List<com.realmatjip.app.domain.model.GooglePlace>>

    /** Google Place Import Preview (스펙 §14). */
    suspend fun importPreview(placeId: String, forceNew: Boolean = false): ApiResult<com.realmatjip.app.domain.model.GoogleImportPreview>

    /** Google Place Import Commit (스펙 §15~§16). */
    suspend fun importCommit(placeId: String, forceNew: Boolean = false): ApiResult<com.realmatjip.app.domain.model.GoogleImportCommit>
}
