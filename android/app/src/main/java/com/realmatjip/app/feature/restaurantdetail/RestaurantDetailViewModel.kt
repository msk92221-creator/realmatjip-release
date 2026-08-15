package com.realmatjip.app.feature.restaurantdetail

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewsPage
import com.realmatjip.app.domain.repository.AdminRepository
import com.realmatjip.app.domain.repository.FavoriteRepository
import com.realmatjip.app.domain.repository.RecentRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class RestaurantDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val restaurantRepository: RestaurantRepository,
    private val adminRepository: AdminRepository,
    private val favoriteRepository: FavoriteRepository,
    private val recentRepository: RecentRepository,
    settingsDataStore: AppSettings,
) : ViewModel() {

    val restaurantId: String = savedStateHandle.get<String>("restaurantId").orEmpty()

    data class UiState(
        val detail: RestaurantDetail? = null,
        val detailLoading: Boolean = true,
        val detailError: ApiError? = null,
        val detailErrorDetail: String? = null,
        val reviews: ReviewsPage? = null,
        val reviewsLoading: Boolean = false,
        val reviewsError: ApiError? = null,
        val adFilter: AdFilter = AdFilter.BASIC,
        val isFavorite: Boolean = false,
        val developerMode: Boolean = false,
        val job: JobInfo? = null,
        val jobError: String? = null,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    /** 잡 폴링 주기 — 진행 중에만 폴링하고 완료 시 중단 (스펙 §21). 테스트에서 교체 가능. */
    var pollIntervalMs: Long = 1500L

    init {
        favoriteRepository.isFavorite(restaurantId)
            .onEach { _uiState.value = _uiState.value.copy(isFavorite = it) }
            .launchIn(viewModelScope)
        settingsDataStore.developerMode
            .onEach { _uiState.value = _uiState.value.copy(developerMode = it) }
            .launchIn(viewModelScope)

        viewModelScope.launch {
            val defaultFilter = settingsDataStore.defaultAdFilter.first()
            _uiState.value = _uiState.value.copy(adFilter = defaultFilter)
            load()
        }
    }

    fun load() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(detailLoading = true, detailError = null)
            when (val result = restaurantRepository.detail(restaurantId)) {
                is ApiResult.Success -> {
                    _uiState.value = _uiState.value.copy(
                        detail = result.data,
                        detailLoading = false,
                    )
                    recordRecent(result.data)
                }
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        detailLoading = false,
                        detailError = result.error,
                        detailErrorDetail = result.detail,
                    )
            }
            loadReviews()
        }
    }

    fun refreshAfterJob() {
        viewModelScope.launch {
            when (val result = restaurantRepository.detail(restaurantId)) {
                is ApiResult.Success -> {
                    _uiState.value = _uiState.value.copy(detail = result.data)
                    recordRecent(result.data)
                }
                else -> Unit
            }
        }
    }

    fun setAdFilter(filter: AdFilter) {
        if (filter == _uiState.value.adFilter) return
        _uiState.value = _uiState.value.copy(adFilter = filter)
        loadReviews()
    }

    fun toggleFavorite() {
        val detail = _uiState.value.detail ?: return
        viewModelScope.launch {
            if (_uiState.value.isFavorite) {
                favoriteRepository.remove(detail.id)
            } else {
                favoriteRepository.add(detail.id, detail.name, detail.category, detail.primaryScore)
            }
        }
    }

    /** 수동 라벨(스펙 §13) — 사람 판정이 LLM보다 우선. 저장 후 리뷰 목록 갱신. */
    fun setManualLabel(reviewId: String, label: String?) {
        viewModelScope.launch {
            when (val result = restaurantRepository.setLabel(reviewId, label)) {
                is ApiResult.Success -> loadReviews()
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(jobError = result.error.name)
            }
        }
    }

    /** [점수 다시 계산] — 잡 진행률 폴링, 완료 후 점수 변경 확인 (스펙 §13, §21). */
    fun recalculate() {
        if (_uiState.value.job?.isFinished == false) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(jobError = null, job = null)
            when (val start = adminRepository.recalculate()) {
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(jobError = start.error.name)
                is ApiResult.Success -> pollJob(start.data)
            }
        }
    }

    private suspend fun pollJob(jobId: Int) {
        while (viewModelScope.coroutineContext.isActive) {
            when (val result = adminRepository.job(jobId)) {
                is ApiResult.Success -> {
                    _uiState.value = _uiState.value.copy(job = result.data)
                    if (result.data.isFinished) {
                        if (result.data.status == "done") refreshAfterJob()
                        else _uiState.value = _uiState.value.copy(jobError = result.data.error)
                        return
                    }
                }
                is ApiResult.Failure -> {
                    _uiState.value = _uiState.value.copy(jobError = result.error.name)
                    return
                }
            }
            delay(pollIntervalMs)
        }
    }

    private suspend fun recordRecent(detail: RestaurantDetail) {
        recentRepository.record(detail.id, detail.name, detail.category, detail.primaryScore)
    }

    private fun loadReviews() {
        val filter = _uiState.value.adFilter
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(reviewsLoading = true, reviewsError = null)
            when (val result = restaurantRepository.reviews(restaurantId, filter)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(reviewsLoading = false, reviews = result.data)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(reviewsLoading = false, reviewsError = result.error)
            }
        }
    }
}
