package com.realmatjip.app.data.restaurant

import com.realmatjip.app.core.database.dao.DetailCacheDao
import com.realmatjip.app.core.database.entity.DetailCacheEntity
import com.realmatjip.app.core.network.ApiClient
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.ConnectionSettingsHolder
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class RestaurantRepositoryImplTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: RestaurantRepositoryImpl
    private lateinit var cacheDao: FakeDetailCacheDao

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val holder = ConnectionSettingsHolder().apply {
            update(server.url("/").toString().trimEnd('/'), "")
        }
        val apiClient = ApiClient(OkHttpClient(), json(), holder)
        cacheDao = FakeDetailCacheDao()
        repository = RestaurantRepositoryImpl(apiClient, json(), cacheDao)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun json() = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = true }

    @Test
    fun `목록 조회 성공 - Phase 1 응답 형식 파싱`() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """
                {"algorithm_version": "v0.1-phase0", "count": 1, "items": [
                  {"id": "rest-d", "name": "충무노포국밥", "category": "돼지국밥",
                   "lat": 37.56, "lng": 127.01, "overall_a": 78.8, "overall_b": 76.2,
                   "n_raw": 16, "n_eff": 6.9, "evidence_strength": 0.46,
                   "evidence_label": "보통", "local_badge": true, "manipulation_score": 0.0}
                ]}
                """.trimIndent()
            )
        )
        val result = repository.search(localOnly = true, minOverall = 70.0)
        assertTrue(result is ApiResult.Success)
        assertEquals(1, (result as ApiResult.Success).data.size)
        assertEquals("충무노포국밥", result.data[0].name)

        val request = server.takeRequest()
        assertTrue(request.path!!.startsWith("/api/restaurants"))
        assertTrue(request.path!!.contains("local_only=true"))
        assertTrue(request.path!!.contains("min_overall=70.0"))
    }

    @Test
    fun `bbox 파라미터 전달`() = runTest {
        server.enqueue(MockResponse().setBody("{\"items\": [], \"count\": 0}"))
        repository.search(bbox = "37.5,126.9,37.6,127.1")
        assertTrue(server.takeRequest().path!!.contains("bbox=37.5%2C126.9%2C37.6%2C127.1"))
    }

    @Test
    fun `401은 UNAUTHORIZED로 매핑`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\": \"no\"}"))
        val result = repository.search()
        assertTrue(result is ApiResult.Failure)
        assertEquals(ApiError.UNAUTHORIZED, (result as ApiResult.Failure).error)
    }

    @Test
    fun `연결 실패는 OFFLINE로 매핑`() = runTest {
        server.shutdown()
        val result = repository.search()
        assertTrue(result is ApiResult.Failure)
        assertEquals(ApiError.OFFLINE, (result as ApiResult.Failure).error)
    }

    @Test
    fun `수동 라벨 요청 본문 검증`() = runTest {
        server.enqueue(
            MockResponse().setBody("""{"review_id": "rest-a-001", "label": "normal"}""")
        )
        val result = repository.setLabel("rest-a-001", "normal")
        assertTrue(result is ApiResult.Success)

        val request = server.takeRequest()
        assertEquals("/api/reviews/rest-a-001/label", request.path)
        assertEquals("POST", request.method)
        assertTrue(request.body.readUtf8().contains("\"normal\""))
    }

    @Test
    fun `상세 성공 시 캐시 저장`() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"id": "rest-b", "name": "을지면옥", "category": "냉면",
                    "lat": 37.5, "lng": 127.0, "address": "",
                    "scores": {"overall_a": 76.6, "overall_b": 74.0}, "detail": null}"""
            )
        )
        val result = repository.detail("rest-b")
        assertTrue(result is ApiResult.Success)
        assertEquals(76.6, (result as ApiResult.Success).data.overallA!!, 1e-9)
        assertEquals("rest-b", cacheDao.saved?.restaurantId)
    }

    @Test
    fun `네트워크 실패 시 캐시로 폴백`() = runTest {
        cacheDao.stored = DetailCacheEntity(
            restaurantId = "rest-b",
            json = """{"id": "rest-b", "name": "을지면옥(캐시)", "category": "냉면",
                       "lat": 37.5, "lng": 127.0, "address": "", "scores": {"overall_a": 70.0}}""",
            fetchedAt = System.currentTimeMillis() - 48 * 3600_000L,
        )
        server.shutdown()

        val result = repository.detail("rest-b")
        assertTrue(result is ApiResult.Success)
        val detail = (result as ApiResult.Success).data
        assertTrue(detail.fromCache)
        assertEquals("을지면옥(캐시)", detail.name)
        assertEquals(48L, detail.cacheAgeHours)
    }

    private class FakeDetailCacheDao : DetailCacheDao {
        var stored: DetailCacheEntity? = null
        var saved: DetailCacheEntity? = null

        override suspend fun upsert(entity: DetailCacheEntity) {
            stored = entity
            saved = entity
        }

        override suspend fun get(restaurantId: String): DetailCacheEntity? =
            stored?.takeIf { it.restaurantId == restaurantId }

        override suspend fun clearAll() {
            stored = null
        }
    }
}
