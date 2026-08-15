package com.realmatjip.app.feature.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.userMessage
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val settingsDataStore: AppSettings,
    private val restaurantRepository: RestaurantRepository,
) : ViewModel() {

    data class UiState(
        val backendUrl: String = "",
        val apiToken: String = "",
        val defaultAdFilter: AdFilter = AdFilter.BASIC,
        val developerMode: Boolean = false,
        val urlEdited: Boolean = false,
        val tokenEdited: Boolean = false,
    )

    /** (url 입력값, token 입력값) — null이면 "아직 편집 안 함"(저장값을 그대로 보여준다).
     * 빈 문자열은 "사용자가 지웠다"는 뜻이므로 null과 구분해야 필드를 비울 수 있다. */
    private val edits = MutableStateFlow<Pair<String?, String?>>(null to null)

    val uiState: StateFlow<UiState> = combine(
        settingsDataStore.backendUrl,
        settingsDataStore.apiToken,
        settingsDataStore.defaultAdFilter,
        settingsDataStore.developerMode,
        edits,
    ) { url, token, adFilter, devMode, (editedUrl, editedToken) ->
        UiState(
            backendUrl = editedUrl ?: url,
            apiToken = editedToken ?: token,
            defaultAdFilter = adFilter,
            developerMode = devMode,
            urlEdited = editedUrl != null,
            tokenEdited = editedToken != null,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), UiState())

    data class ConnectionTest(
        val running: Boolean = false,
        val success: String? = null,
        val failure: String? = null,
    )

    private val _connectionTest = MutableStateFlow(ConnectionTest())
    val connectionTest: StateFlow<ConnectionTest> = _connectionTest.asStateFlow()

    fun onUrlChange(url: String) {
        edits.value = edits.value.copy(first = url)
    }

    fun onTokenChange(token: String) {
        edits.value = edits.value.copy(second = token)
    }

    fun saveConnection() {
        viewModelScope.launch { saveCurrentEdits() }
    }

    fun setDefaultAdFilter(filter: AdFilter) {
        viewModelScope.launch { settingsDataStore.setDefaultAdFilter(filter) }
    }

    fun setDeveloperMode(enabled: Boolean) {
        viewModelScope.launch { settingsDataStore.setDeveloperMode(enabled) }
    }

    fun testConnection() {
        viewModelScope.launch {
            _connectionTest.value = ConnectionTest(running = true)
            saveCurrentEdits()
            when (val result = restaurantRepository.testConnection()) {
                is ApiResult.Success ->
                    _connectionTest.value = ConnectionTest(success = "연결 성공 — ${result.data}")
                is ApiResult.Failure ->
                    _connectionTest.value = ConnectionTest(
                        failure = result.error.userMessage() + " (${result.detail ?: ""})",
                    )
            }
        }
    }

    /** 편집된 항목만 저장한다. 빈 값으로 저장하면 기본 주소로 되돌아간다(SettingsDataStore 참고). */
    private suspend fun saveCurrentEdits() {
        val (url, token) = edits.value
        if (url != null) settingsDataStore.setBackendUrl(url)
        if (token != null) settingsDataStore.setApiToken(token)
        edits.value = null to null
    }
}
