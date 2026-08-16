package com.realmatjip.app.feature.map

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.BuildConfig
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.location.LocationProvider
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
import java.util.Locale
import javax.inject.Inject

/** 지도 (스펙 §15) — 카메라 정지 → debounce → bbox 검색 → 마커 업데이트.
 * 지도 SDK 타입은 화면 계층에만 존재하고 ViewModel은 좌표만 다룬다 (D4 분리). */
@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class MapViewModel @Inject constructor(
    private val restaurantRepository: RestaurantRepository,
    private val locationProvider: LocationProvider,
) : ViewModel() {

    data class UiState(
        val hasMapsKey: Boolean = BuildConfig.MAPS_API_KEY.isNotBlank(),
        val loading: Boolean = false,
        val restaurants: List<Restaurant> = emptyList(),
        val selectedId: String? = null,
        val error: ApiError? = null,
        val errorDetail: String? = null,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private val regionRequests = MutableSharedFlow<String>(
        extraBufferCapacity = 1,
        onBufferOverflow = kotlinx.coroutines.channels.BufferOverflow.DROP_OLDEST,
    )

    init {
        regionRequests
            .drop(1) // 초기 위치 이동은 무시하고 이후 이동만 검색
            .debounce(500)
            .onEach { bbox -> searchRegion(bbox) }
            .launchIn(viewModelScope)

        // 첫 로드: 위치와 무관하게 전체 상위 결과
        viewModelScope.launch {
            when (val result = restaurantRepository.search(limit = 60)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(restaurants = result.data)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(error = result.error, errorDetail = result.detail)
            }
        }
    }

    fun onCameraIdle(swLat: Double, swLng: Double, neLat: Double, neLng: Double) {
        regionRequests.tryEmit(formatBbox(swLat, swLng, neLat, neLng))
    }

    fun select(restaurantId: String?) {
        _uiState.value = _uiState.value.copy(selectedId = restaurantId)
    }

    // ── 내 위치 버튼: 좌표만 노출하고 카메라 이동은 화면 계층에서 (D4) ──

    private val _cameraTarget = MutableStateFlow<Pair<Double, Double>?>(null)
    val cameraTarget: StateFlow<Pair<Double, Double>?> = _cameraTarget.asStateFlow()
    var locationFailed = MutableStateFlow(false)

    fun moveToMyLocation() {
        viewModelScope.launch {
            locationFailed.value = false
            _cameraTarget.value = locationProvider.currentLocation()
                ?: run { locationFailed.value = true; null }
        }
    }

    /** 임포트/재계산 완료 후 마커 새로고침. */
    fun refresh() {
        viewModelScope.launch {
            when (val result = restaurantRepository.search(limit = 60)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(restaurants = result.data)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(error = result.error, errorDetail = result.detail)
            }
        }
    }

    fun dismissError() {
        _uiState.value = _uiState.value.copy(error = null, errorDetail = null)
    }

    private suspend fun searchRegion(bbox: String) {
        _uiState.value = _uiState.value.copy(loading = true)
        when (val result = restaurantRepository.search(bbox = bbox, limit = 60)) {
            is ApiResult.Success ->
                _uiState.value = _uiState.value.copy(loading = false, restaurants = result.data)
            is ApiResult.Failure ->
                _uiState.value = _uiState.value.copy(loading = false, error = result.error, errorDetail = result.detail)
        }
    }

    companion object {
        /** Backend bbox 쿼리 형식: "lat1,lng1,lat2,lng2" — 좌표 순서는 임의(서버가 min/max 처리). */
        fun formatBbox(swLat: Double, swLng: Double, neLat: Double, neLng: Double): String =
            String.format(Locale.ROOT, "%.5f,%.5f,%.5f,%.5f", swLat, swLng, neLat, neLng)
    }
}
