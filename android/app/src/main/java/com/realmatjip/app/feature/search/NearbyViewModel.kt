package com.realmatjip.app.feature.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.location.LocationProvider
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.userMessage
import com.realmatjip.app.domain.model.GooglePlace
import com.realmatjip.app.domain.repository.AdminRepository
import com.realmatjip.app.domain.repository.ProviderRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 주변 탐색 — 현재 위치 기준 맛집 발견 → 선택 임포트 → LLM 분석 → 점수 재계산까지 자동.
 * 임포트만 하고 홈에 안 뜨는 불상사를 막는다 (분석/재계산 없으면 목록에서 보이지 않음).
 */
@HiltViewModel
class NearbyViewModel @Inject constructor(
    private val locationProvider: LocationProvider,
    private val providerRepository: ProviderRepository,
    private val adminRepository: AdminRepository,
) : ViewModel() {

    enum class Phase { Idle, Locating, Searching, Results, Importing, Analyzing, Recalculating, Done, Failed }

    data class UiState(
        val phase: Phase = Phase.Idle,
        val myLat: Double? = null,
        val myLng: Double? = null,
        val results: List<GooglePlace> = emptyList(),
        val busyPlaceId: String? = null,
        val importedCount: Int = 0,
        val message: String? = null,
    ) {
        val working: Boolean
            get() = phase == Phase.Locating || phase == Phase.Searching ||
                phase == Phase.Importing || phase == Phase.Analyzing || phase == Phase.Recalculating
    }

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    /** 테스트에서 폴링 주기를 줄인다. */
    var pollIntervalMs: Long = 2000L

    fun explore() {
        if (_uiState.value.working) return
        viewModelScope.launch {
            _uiState.value = UiState(phase = Phase.Locating)
            val location = locationProvider.currentLocation()
            if (location == null) {
                _uiState.value = UiState(
                    phase = Phase.Failed,
                    message = "위치를 가져올 수 없어요 — GPS 켜고 다시 시도해 주세요",
                )
                return@launch
            }
            val (lat, lng) = location
            _uiState.value = _uiState.value.copy(phase = Phase.Searching, myLat = lat, myLng = lng)
            when (val result = providerRepository.search("맛집", lat, lng)) {
                is ApiResult.Success -> {
                    if (result.data.isEmpty()) {
                        _uiState.value = _uiState.value.copy(
                            phase = Phase.Failed, message = "주변에 결과가 없어요",
                        )
                    } else {
                        _uiState.value = _uiState.value.copy(phase = Phase.Results, results = result.data)
                    }
                }
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        phase = Phase.Failed, message = result.error.userMessage(),
                    )
            }
        }
    }

    fun reset() {
        _uiState.value = UiState()
    }

    /** 개별 임포트 — 마지막 임포트 후 분석+재계산 자동 실행. */
    fun importPlace(place: GooglePlace) {
        if (_uiState.value.working) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(phase = Phase.Importing, busyPlaceId = place.placeId)
            when (val result = providerRepository.importCommit(place.placeId)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(
                        busyPlaceId = null,
                        importedCount = _uiState.value.importedCount + 1,
                        results = _uiState.value.results.filter { it.placeId != place.placeId },
                        phase = Phase.Results,
                    )
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        busyPlaceId = null, phase = Phase.Results,
                        message = "임포트 실패: ${result.error.userMessage()}",
                    )
            }
        }
    }

    /** 결과 전체 임포트 후 분석+재계산까지 한 번에. */
    fun importAllAndFinalize() {
        val targets = _uiState.value.results
        if (targets.isEmpty() || _uiState.value.working) return
        viewModelScope.launch {
            var ok = 0
            targets.forEach { place ->
                _uiState.value = _uiState.value.copy(phase = Phase.Importing, busyPlaceId = place.placeId)
                if (providerRepository.importCommit(place.placeId) is ApiResult.Success) ok++
            }
            _uiState.value = _uiState.value.copy(busyPlaceId = null, importedCount = ok, results = emptyList())
            if (ok == 0) {
                _uiState.value = _uiState.value.copy(phase = Phase.Failed, message = "임포트에 실패했어요")
                return@launch
            }
            finalize()
        }
    }

    /** 임포트된 리뷰 LLM 분석 → 점수 재계산 → 완료. 실패해도 다시 시도 가능. */
    fun finalize() {
        viewModelScope.launch {
            val analyzed = runJob(Phase.Analyzing) { adminRepository.analyzePending() }
            val recalculated = runJob(Phase.Recalculating) { adminRepository.recalculate() }
            _uiState.value = if (analyzed && recalculated) {
                _uiState.value.copy(
                    phase = Phase.Done,
                    message = "${_uiState.value.importedCount}곳 추가 완료 — 홈에서 확인하세요",
                )
            } else {
                _uiState.value.copy(
                    phase = Phase.Failed,
                    message = "임포트는 됐지만 분석/재계산이 실패했어요 — Developer 화면에서 다시 실행해 주세요",
                )
            }
        }
    }

    private suspend fun runJob(phase: Phase, start: suspend () -> ApiResult<Int>): Boolean {
        _uiState.value = _uiState.value.copy(phase = phase)
        return when (val started = start()) {
            is ApiResult.Failure -> false
            is ApiResult.Success -> {
                while (viewModelScope.coroutineContext.isActive) {
                    when (val polled = adminRepository.job(started.data)) {
                        is ApiResult.Failure -> return false
                        is ApiResult.Success -> {
                            val status = polled.data.status
                            if (status == "done") return true
                            if (status == "failed") return false
                        }
                    }
                    delay(pollIntervalMs)
                }
                false
            }
        }
    }
}
