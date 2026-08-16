package com.realmatjip.app.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.core.location.LocationProvider
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.userMessage
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.RecentRestaurant
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.repository.ProviderRepository
import com.realmatjip.app.domain.repository.RecentRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Locale
import javax.inject.Inject

/** 홈 — 기준 지역 설정 후 그 지역의 찐맛집 Top만 보여준다 (지역 미설정 시 목록 없음). */
@HiltViewModel
class HomeViewModel @Inject constructor(
    private val restaurantRepository: RestaurantRepository,
    private val providerRepository: ProviderRepository,
    private val locationProvider: LocationProvider,
    private val settings: AppSettings,
    recentRepository: RecentRepository,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val regionLabel: String = "",
        val regionLat: Double? = null,
        val regionLng: Double? = null,
        val locating: Boolean = false,
        val topRestaurants: List<Restaurant> = emptyList(),
        val localRestaurants: List<Restaurant> = emptyList(),
        val recents: List<RecentRestaurant> = emptyList(),
        val meta: BackendMeta? = null,
        val error: ApiError? = null,
        val errorDetail: String? = null,
        val message: String? = null,
    ) {
        val hasRegion: Boolean get() = regionLat != null && regionLng != null
    }

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            recentRepository.recents.collect { recents ->
                _uiState.value = _uiState.value.copy(recents = recents)
            }
        }
        // 저장된 기준 지역 복원 — 있으면 그 지역 기준으로 로드
        viewModelScope.launch {
            val label = settings.homeRegionLabel.first()
            val lat = settings.homeRegionLat.first()
            val lng = settings.homeRegionLng.first()
            if (label.isNotBlank() && lat != 0f && lng != 0f) {
                _uiState.value = _uiState.value.copy(
                    regionLabel = label, regionLat = lat.toDouble(), regionLng = lng.toDouble(),
                )
                refresh()
            } else {
                _uiState.value = _uiState.value.copy(loading = false)
            }
        }
    }

    /** GPS로 내 위치를 기준 지역으로. */
    fun useMyLocation() {
        if (_uiState.value.locating) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(locating = true, message = null)
            val location = locationProvider.currentLocation()
            if (location == null) {
                _uiState.value = _uiState.value.copy(
                    locating = false,
                    message = "위치를 가져올 수 없어요 — GPS 켜고 다시 시도해 주세요",
                )
                return@launch
            }
            applyRegion("내 위치", location.first, location.second)
        }
    }

    /** 지역명 검색 — 구글에서 지역 좌표를 얻어 기준 지역으로. */
    fun searchRegion(query: String) {
        val q = query.trim()
        if (q.isEmpty()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(locating = true, message = null)
            when (val result = providerRepository.search(q)) {
                is ApiResult.Success -> {
                    val first = result.data.firstOrNull()
                    if (first == null) {
                        _uiState.value = _uiState.value.copy(
                            locating = false, message = "'$q' 검색 결과가 없어요",
                        )
                    } else {
                        applyRegion(first.name, first.lat, first.lng)
                    }
                }
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        locating = false, message = "지역 검색 실패: ${result.error.userMessage()}",
                    )
            }
        }
    }

    private suspend fun applyRegion(label: String, lat: Double, lng: Double) {
        settings.setHomeRegion(label, lat, lng)
        _uiState.value = _uiState.value.copy(
            locating = false, regionLabel = label, regionLat = lat, regionLng = lng,
        )
        refresh()
    }

    fun clearMessage() {
        _uiState.value = _uiState.value.copy(message = null)
    }

    fun refresh() {
        val state = _uiState.value
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(loading = true, error = null)
            val bbox = state.regionLat?.let { lat ->
                state.regionLng?.let { lng -> formatBbox(lat, lng) }
            }
            val top = restaurantRepository.search(sort = "overall_a", limit = 5, bbox = bbox)
            val local = restaurantRepository.search(localOnly = true, limit = 5, bbox = bbox)
            val meta = restaurantRepository.meta()

            var next = _uiState.value.copy(loading = false)
            next = when (top) {
                is ApiResult.Success -> next.copy(topRestaurants = top.data)
                is ApiResult.Failure -> next.copy(error = top.error, errorDetail = top.detail)
            }
            if (local is ApiResult.Success) {
                next = next.copy(localRestaurants = local.data)
            } else if (next.error == null && local is ApiResult.Failure) {
                next = next.copy(error = local.error, errorDetail = local.detail)
            }
            if (meta is ApiResult.Success) {
                next = next.copy(meta = meta.data)
            }
            _uiState.value = next
        }
    }

    companion object {
        /** 기준 지역 주변 박스 — 약 6km x 7km (도시 단위 근방). */
        fun formatBbox(lat: Double, lng: Double): String =
            String.format(
                Locale.ROOT, "%.5f,%.5f,%.5f,%.5f",
                lat - 0.055, lng - 0.065, lat + 0.055, lng + 0.065,
            )
    }
}
