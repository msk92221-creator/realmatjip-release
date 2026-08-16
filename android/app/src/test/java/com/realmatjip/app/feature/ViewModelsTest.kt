package com.realmatjip.app.feature

import androidx.lifecycle.SavedStateHandle
import com.realmatjip.app.FakeAdminRepository
import com.realmatjip.app.FakeAppSettings
import com.realmatjip.app.FakeFavoriteRepository
import com.realmatjip.app.FakeProviderRepository
import com.realmatjip.app.FakeRecentRepository
import com.realmatjip.app.FakeRestaurantRepository
import com.realmatjip.app.MainDispatcherRule
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.feature.home.HomeViewModel
import com.realmatjip.app.feature.map.MapViewModel
import com.realmatjip.app.feature.restaurantdetail.RestaurantDetailViewModel
import com.realmatjip.app.feature.search.SearchViewModel
import com.realmatjip.app.testDetail
import com.realmatjip.app.testRestaurant
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class HomeViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `찐맛집 Top과 로컬맛집 Top을 함께 로드`() {
        val restaurantRepo = FakeRestaurantRepository().apply {
            restaurants = listOf(testRestaurant())
        }
        val recentRepo = FakeRecentRepository()
        val viewModel = HomeViewModel(
            restaurantRepo, FakeProviderRepository(),
            FakeLocationProvider(),
            FakeAppSettings(
                homeRegionLabel = MutableStateFlow("테스트지역"),
                homeRegionLat = MutableStateFlow(37.5f),
                homeRegionLng = MutableStateFlow(127.0f),
            ),
            recentRepo,
        )
        mainDispatcherRule.advanceUntilIdle()

        val state = viewModel.uiState.value
        assertEquals(listOf(testRestaurant()), state.topRestaurants)
        assertEquals(listOf(testRestaurant()), state.localRestaurants)
        assertNull(state.error)
        assertEquals("v0.1-phase0", state.meta?.algorithmVersion)
    }

    @Test
    fun `최근 본 맛집 반영`() {
        val restaurantRepo = FakeRestaurantRepository()
        val recentRepo = FakeRecentRepository()
        val viewModel = HomeViewModel(
            restaurantRepo, FakeProviderRepository(),
            FakeLocationProvider(),
            FakeAppSettings(
                homeRegionLabel = MutableStateFlow("테스트지역"),
                homeRegionLat = MutableStateFlow(37.5f),
                homeRegionLng = MutableStateFlow(127.0f),
            ),
            recentRepo,
        )
        mainDispatcherRule.advanceUntilIdle()

        kotlinx.coroutines.runBlocking { recentRepo.record("rest-b", "을지면옥", "냉면", 76.6) }
        mainDispatcherRule.advanceUntilIdle()
        assertEquals(1, viewModel.uiState.value.recents.size)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SearchViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private fun viewModel(repo: FakeRestaurantRepository): SearchViewModel = SearchViewModel(repo)

    @Test
    fun `초기 로드는 전체 조회`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(repo)
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(1, repo.searchCalls.size)
        // ViewModel은 필터 값을 리포지토리에 그대로 전달 (쿼리 파라미터 정규화는 리포지토리 담당)
        assertEquals("false", repo.searchCalls[0]["local_only"])
        assertEquals(null, repo.searchCalls[0]["min_overall"])
    }

    @Test
    fun `찐맛집 칩은 min_overall 70을 적용`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(repo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.onToggleTrueGem()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("70.0", repo.searchCalls.last()["min_overall"])
    }

    @Test
    fun `로컬 칩은 local_only를 적용`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(repo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.onToggleLocal()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("true", repo.searchCalls.last()["local_only"])
    }

    @Test
    fun `검색어 전달`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(repo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.onQueryChange("면옥")
        viewModel.search()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("면옥", repo.searchCalls.last()["q"])
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class MapViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `bbox 포맷 - 5자리 정밀도`() {
        assertEquals(
            "37.54123,126.98765,37.60987,127.05432",
            MapViewModel.formatBbox(37.54123, 126.98765, 37.60987, 127.05432),
        )
    }

    @Test
    fun `초기 로드 후 카메라 이동 시 bbox 검색`() {
        val repo = FakeRestaurantRepository().apply { restaurants = listOf(testRestaurant()) }
        val viewModel = MapViewModel(repo, FakeLocationProvider())
        mainDispatcherRule.advanceUntilIdle()
        assertEquals(1, repo.searchCalls.size)

        // 첫 이벤트(지도 로드 직후)는 무시되고, 이후 카메라 이동부터 검색한다 (스펙 §15)
        viewModel.onCameraIdle(37.50, 126.90, 37.55, 126.95)
        mainDispatcherRule.advanceUntilIdle()
        assertEquals(1, repo.searchCalls.size)

        viewModel.onCameraIdle(37.54, 126.99, 37.60, 127.05)
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("37.54000,126.99000,37.60000,127.05000", repo.searchCalls.last()["bbox"])
    }

    @Test
    fun `마커 선택`() {
        val repo = FakeRestaurantRepository()
        val viewModel = MapViewModel(repo, FakeLocationProvider())
        mainDispatcherRule.advanceUntilIdle()

        viewModel.select("rest-b")
        assertEquals("rest-b", viewModel.uiState.value.selectedId)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class RestaurantDetailViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private fun viewModel(
        restaurantRepo: FakeRestaurantRepository = FakeRestaurantRepository(),
        adminRepo: FakeAdminRepository = FakeAdminRepository(),
        favoriteRepo: FakeFavoriteRepository = FakeFavoriteRepository(),
        recentRepo: FakeRecentRepository = FakeRecentRepository(),
        settings: FakeAppSettings = FakeAppSettings(),
        savedState: SavedStateHandle = SavedStateHandle(mapOf("restaurantId" to "rest-b")),
    ) = RestaurantDetailViewModel(
        savedState, restaurantRepo, adminRepo, favoriteRepo, recentRepo, settings,
    )

    @Test
    fun `상세 로드 후 최근 본 맛집 기록`() {
        val recentRepo = FakeRecentRepository()
        val viewModel = viewModel(recentRepo = recentRepo)
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("rest-b", viewModel.restaurantId)
        assertEquals("을지면옥", viewModel.uiState.value.detail?.name)
        assertTrue(recentRepo.recorded.contains("rest-b"))
    }

    @Test
    fun `광고 필터 변경 시 재조회`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(restaurantRepo = repo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.setAdFilter(AdFilter.VERY_STRICT)
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(AdFilter.VERY_STRICT, viewModel.uiState.value.adFilter)
        assertEquals(AdFilter.VERY_STRICT, viewModel.uiState.value.reviews?.adFilter)
    }

    @Test
    fun `수동 라벨 저장`() {
        val repo = FakeRestaurantRepository()
        val viewModel = viewModel(restaurantRepo = repo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.setManualLabel("rest-b-001", "normal")
        mainDispatcherRule.advanceUntilIdle()

        assertEquals("normal", repo.labels["rest-b-001"])
    }

    @Test
    fun `재계산 잡 폴링 후 점수 변경 확인`() {
        val restaurantRepo = FakeRestaurantRepository().apply {
            detailResponse = testDetail(overallA = 76.6)
        }
        val adminRepo = FakeAdminRepository()
        val viewModel = viewModel(restaurantRepo = restaurantRepo, adminRepo = adminRepo)
        viewModel.pollIntervalMs = 10
        mainDispatcherRule.advanceUntilIdle()
        assertEquals(76.6, viewModel.uiState.value.detail?.overallA!!, 1e-9)

        // 재계산 완료 후 서버 점수가 바뀐 상황
        restaurantRepo.detailResponse = testDetail(overallA = 79.1)
        viewModel.recalculate()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(1, adminRepo.recalculateCalls)
        val job = viewModel.uiState.value.job
        assertNotNull(job)
        assertEquals("done", job!!.status)
        assertEquals(5, job.done)
        assertEquals(79.1, viewModel.uiState.value.detail?.overallA!!, 1e-9)
    }

    @Test
    fun `즐겨찾기 토글`() {
        val favoriteRepo = FakeFavoriteRepository()
        val viewModel = viewModel(favoriteRepo = favoriteRepo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.toggleFavorite()
        mainDispatcherRule.advanceUntilIdle()

        assertTrue(favoriteRepo.added.contains("rest-b"))
        assertTrue(viewModel.uiState.value.isFavorite)
    }
}


/** 지도 테스트용 — 항상 좌표 하나 반환. */
class FakeLocationProvider : com.realmatjip.app.core.location.LocationProvider {
    override suspend fun currentLocation(): Pair<Double, Double>? = 37.5 to 127.0
}
