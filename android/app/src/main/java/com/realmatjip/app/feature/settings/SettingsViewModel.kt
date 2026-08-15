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

    private val edits = MutableStateFlow(Pair("", "")) // (url 입력값, token 입력값)

    val uiState: StateFlow<UiState> = combine(
        settingsDataStore.backendUrl,
        settingsDataStore.apiToken,
        settingsDataStore.defaultAdFilter,
        settingsDataStore.developerMode,
        edits,
    ) { url, token, adFilter, devMode, (editedUrl, editedToken) ->
        UiState(
            backendUrl = if (editedUrl.isNotEmpty()) editedUrl else url,
            apiToken = if (editedToken.isNotEmpty()) editedToken else token,
            defaultAdFilter = adFilter,
            developerMode = devMode,
            urlEdited = editedUrl.isNotEmpty(),
            tokenEdited = editedToken.isNotEmpty(),
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
        val (url, token) = edits.value
        viewModelScope.launch {
            if (url.isNotEmpty()) settingsDataStore.setBackendUrl(url)
            if (token.isNotEmpty()) settingsDataStore.setApiToken(token)
            edits.value = Pair("", "")
        }
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

    private suspend fun saveCurrentEdits() {
        val (url, token) = edits.value
        if (url.isNotEmpty()) settingsDataStore.setBackendUrl(url)
        if (token.isNotEmpty()) settingsDataStore.setApiToken(token)
        edits.value = Pair("", "")
    }
}
