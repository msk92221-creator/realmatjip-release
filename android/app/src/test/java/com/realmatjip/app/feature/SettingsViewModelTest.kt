package com.realmatjip.app.feature

import com.realmatjip.app.FakeRestaurantRepository
import com.realmatjip.app.MainDispatcherRule
import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.feature.settings.SettingsViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/** 설정 화면의 편집 버퍼 동작 — "비어 있음"과 "편집 안 함"이 섞이면 필드를 지울 수 없게 된다. */
@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private class RecordingAppSettings(
        savedUrl: String = "http://10.0.2.2:8000",
    ) : AppSettings {
        val urlFlow = MutableStateFlow(savedUrl)
        var savedUrls = mutableListOf<String>()

        override val backendUrl: Flow<String> = urlFlow
        override val apiToken: Flow<String> = MutableStateFlow("")
        override val defaultAdFilter: Flow<AdFilter> = MutableStateFlow(AdFilter.BASIC)
        override val developerMode: Flow<Boolean> = MutableStateFlow(false)
        override val homeRegionLabel: Flow<String> = MutableStateFlow("")
        override val homeRegionLat: Flow<Float> = MutableStateFlow(0f)
        override val homeRegionLng: Flow<Float> = MutableStateFlow(0f)

        override suspend fun setHomeRegion(label: String, lat: Double, lng: Double) = Unit
        override suspend fun setBackendUrl(url: String) {
            savedUrls += url
            urlFlow.value = url
        }

        override suspend fun setApiToken(token: String) = Unit
        override suspend fun setDefaultAdFilter(filter: AdFilter) = Unit
        override suspend fun setDeveloperMode(enabled: Boolean) = Unit
    }

    @Test
    fun `주소를 전부 지우면 빈 상태가 유지된다`() = runTest(mainDispatcherRule.dispatcher) {
        val settings = RecordingAppSettings()
        val viewModel = SettingsViewModel(settings, FakeRestaurantRepository())
        val collector = launch { viewModel.uiState.collect {} }

        viewModel.onUrlChange("")
        mainDispatcherRule.advanceUntilIdle()

        // 회귀 방지: 예전에는 저장값("http://10.0.2.2:8000")으로 되돌아가 필드를 비울 수 없었다.
        assertEquals("", viewModel.uiState.value.backendUrl)
        collector.cancel()
    }

    @Test
    fun `지우고 새 주소를 입력하면 그대로 반영된다`() = runTest(mainDispatcherRule.dispatcher) {
        val settings = RecordingAppSettings()
        val viewModel = SettingsViewModel(settings, FakeRestaurantRepository())
        val collector = launch { viewModel.uiState.collect {} }

        viewModel.onUrlChange("")
        viewModel.onUrlChange("http://100.79.12.113:8000")
        viewModel.saveConnection()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(listOf("http://100.79.12.113:8000"), settings.savedUrls)
        assertEquals("http://100.79.12.113:8000", viewModel.uiState.value.backendUrl)
        collector.cancel()
    }

    @Test
    fun `편집하지 않고 저장하면 아무것도 덮어쓰지 않는다`() = runTest(mainDispatcherRule.dispatcher) {
        val settings = RecordingAppSettings()
        val viewModel = SettingsViewModel(settings, FakeRestaurantRepository())
        val collector = launch { viewModel.uiState.collect {} }

        viewModel.saveConnection()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(emptyList<String>(), settings.savedUrls)
        collector.cancel()
    }
}
