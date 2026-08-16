package com.realmatjip.app.feature.search

import com.realmatjip.app.FakeAdminRepository
import com.realmatjip.app.FakeProviderRepository
import com.realmatjip.app.MainDispatcherRule
import com.realmatjip.app.core.location.LocationProvider
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.GooglePlace
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class NearbyViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private class FakeLocation(var result: Pair<Double, Double>? = 37.0 to 127.0) : LocationProvider {
        override suspend fun currentLocation(): Pair<Double, Double>? = result
    }

    private fun place(id: String, name: String = id) = GooglePlace(
        placeId = id, name = name, formattedAddress = "서울",
        lat = 37.0, lng = 127.0, primaryType = "restaurant",
        rating = 4.5, userRatingCount = 100, googleMapsUrl = "",
    )

    private fun viewModel(
        location: LocationProvider,
        admin: FakeAdminRepository = FakeAdminRepository(),
        provider: FakeProviderRepository = FakeProviderRepository(),
    ): Triple<NearbyViewModel, FakeAdminRepository, FakeProviderRepository> =
        Triple(NearbyViewModel(location, provider, admin), admin, provider)

    @Test
    fun `주변 탐색 성공 — 위치 받아 검색 결과 표시`() {
        val (vm, _, provider) = viewModel(FakeLocation())
        provider.searchResult = ApiResult.Success(listOf(place("a"), place("b")))

        vm.explore()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(NearbyViewModel.Phase.Results, vm.uiState.value.phase)
        assertEquals(2, vm.uiState.value.results.size)
        assertEquals(37.0, vm.uiState.value.myLat!!, 0.001)
    }

    @Test
    fun `임의 좌표 탐색 - 지도 중심에서 검색`() {
        val (vm, _) = viewModel(FakeLocation(result = null)) to Unit // GPS 미사용 확인용
        val provider = FakeProviderRepository()
        val admin = FakeAdminRepository()
        val vm2 = NearbyViewModel(FakeLocation(result = null), provider, admin)
        provider.searchResult = ApiResult.Success(listOf(place("x")))

        vm2.exploreAt(35.1, 129.0)
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(NearbyViewModel.Phase.Results, vm2.uiState.value.phase)
        assertEquals(1, vm2.uiState.value.results.size)
        assertEquals(35.1, vm2.uiState.value.myLat!!, 0.001)
    }

    @Test
    fun `위치 실패 — 안내 메시지`() {
        val (vm, _, _) = viewModel(FakeLocation(result = null))

        vm.explore()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(NearbyViewModel.Phase.Failed, vm.uiState.value.phase)
        assertTrue(vm.uiState.value.message!!.contains("위치"))
    }

    @Test
    fun `전체 임포트 — 분석과 재계산까지 자동 실행`() {
        val (vm, admin, provider) = viewModel(FakeLocation())
        provider.searchResult = ApiResult.Success(listOf(place("a"), place("b"), place("c")))
        vm.explore()
        mainDispatcherRule.advanceUntilIdle()

        vm.importAllAndFinalize()
        mainDispatcherRule.advanceUntilIdle()

        val state = vm.uiState.value
        assertEquals(NearbyViewModel.Phase.Done, state.phase)
        assertEquals(3, state.importedCount)
        assertEquals(1, admin.analyzePendingCalls)
        assertEquals(1, admin.recalculateCalls)
        assertEquals(0, state.results.size)
        assertTrue(state.message!!.contains("홈에서 확인"))
    }

    @Test
    fun `개별 임포트 — 결과 목록에서 제거`() {
        val (vm, _, provider) = viewModel(FakeLocation())
        provider.searchResult = ApiResult.Success(listOf(place("a"), place("b")))
        vm.explore()
        mainDispatcherRule.advanceUntilIdle()

        vm.importPlace(vm.uiState.value.results.first())
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(NearbyViewModel.Phase.Results, vm.uiState.value.phase)
        assertEquals(1, vm.uiState.value.results.size)
        assertEquals(1, vm.uiState.value.importedCount)
    }

    @Test
    fun `분석 잡 실패 - 안내와 함께 Failed`() {
        val admin = FakeAdminRepository().apply {
            jobScript.clear()
            jobScript.add("failed") // 첫 폴링부터 실패 상태
        }
        val (vm, _, provider) = viewModel(FakeLocation(), admin)
        provider.searchResult = ApiResult.Success(listOf(place("a")))
        vm.explore()
        mainDispatcherRule.advanceUntilIdle()

        vm.importAllAndFinalize()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(NearbyViewModel.Phase.Failed, vm.uiState.value.phase)
        assertTrue(vm.uiState.value.message!!.contains("Developer"))
    }
}
