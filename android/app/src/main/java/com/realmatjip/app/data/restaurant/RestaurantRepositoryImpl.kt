package com.realmatjip.app.data.restaurant

import com.realmatjip.app.core.database.dao.DetailCacheDao
import com.realmatjip.app.core.database.entity.DetailCacheEntity
import com.realmatjip.app.core.network.ApiClient
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.apiCall
import com.realmatjip.app.data.restaurant.dto.LabelRequestDto
import com.realmatjip.app.data.restaurant.dto.RestaurantDetailResponseDto
import com.realmatjip.app.data.restaurant.mapper.toDomain
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewsPage
import com.realmatjip.app.domain.repository.RestaurantRepository
import kotlinx.serialization.json.Json
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class RestaurantRepositoryImpl @Inject constructor(
    private val apiClient: ApiClient,
    private val json: Json,
    private val detailCacheDao: DetailCacheDao,
) : RestaurantRepository {

    private fun api(): RestaurantApi = apiClient.service(RestaurantApi::class)

    override suspend fun search(
        query: String?,
        localOnly: Boolean,
        minOverall: Double?,
        sort: String,
        bbox: String?,
        limit: Int,
    ): ApiResult<List<Restaurant>> = apiCall {
        api().list(
            query = query?.ifBlank { null },
            localOnly = localOnly.takeIf { it },
            minOverall = minOverall,
            sort = sort,
            bbox = bbox,
            limit = limit,
        ).items.map { it.toDomain() }
    }

    override suspend fun detail(id: String): ApiResult<RestaurantDetail> {
        val network = apiCall { api().detail(id) }
        return when (network) {
            is ApiResult.Success -> {
                cache(id, network.data)
                ApiResult.Success(network.data.toDomain())
            }
            is ApiResult.Failure -> {
                val cached = detailCacheDao.get(id)
                if (cached != null) {
                    runCatching { json.decodeFromString(RestaurantDetailResponseDto.serializer(), cached.json) }
                        .onSuccess { dto ->
                            return ApiResult.Success(
                                dto.toDomain(
                                    fromCache = true,
                                    cacheAgeHours = cacheAgeHours(cached.fetchedAt),
                                )
                            )
                        }
                }
                network
            }
        }
    }

    override suspend fun reviews(id: String, filter: AdFilter, limit: Int): ApiResult<ReviewsPage> =
        apiCall { api().reviews(id, filter.queryValue, limit).toDomain() }

    override suspend fun setLabel(reviewId: String, label: String?): ApiResult<Unit> = apiCall {
        api().setLabel(reviewId, LabelRequestDto(label = label))
        Unit
    }

    override suspend fun meta(): ApiResult<BackendMeta> = apiCall { api().meta().toDomain() }

    override suspend fun testConnection(): ApiResult<String> = apiCall {
        val health = apiClient.service(AdminApiTest::class).health()
        "${health.status} · ${health.version}"
    }

    private suspend fun cache(id: String, dto: RestaurantDetailResponseDto) {
        runCatching {
            detailCacheDao.upsert(
                DetailCacheEntity(
                    restaurantId = id,
                    json = json.encodeToString(RestaurantDetailResponseDto.serializer(), dto),
                    fetchedAt = System.currentTimeMillis(),
                )
            )
        }
    }

    private fun cacheAgeHours(fetchedAt: Long): Long =
        TimeUnit.MILLISECONDS.toHours(System.currentTimeMillis() - fetchedAt)
}

/** /health는 restaurant가 아닌 시스템 엔드포인트 — 테스트 편의를 위한 최소 인터페이스 */
private interface AdminApiTest {
    @retrofit2.http.GET("/health")
    suspend fun health(): com.realmatjip.app.data.restaurant.dto.HealthDto
}
