package com.realmatjip.app.feature.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** 검색 필터 (스펙 §14) — '찐맛집' = min_overall 70, '로컬' = local_only.
 * '광고 적은 리뷰'/'가성비'는 목록 API에 필터가 없어 Phase 3로 표기하고 비활성화. */
data class SearchFilters(
    val trueGem: Boolean = false,
    val local: Boolean = false,
) {
    val minOverall: Double? get() = if (trueGem) 70.0 else null
}

@HiltViewModel
class SearchViewModel @Inject constructor(
    private val restaurantRepository: RestaurantRepository,
) : ViewModel() {

    data class UiState(
        val query: String = "",
        val filters: SearchFilters = SearchFilters(),
        val loading: Boolean = false,
        val searched: Boolean = false,
        val results: List<Restaurant> = emptyList(),
        val error: ApiError? = null,
        val errorDetail: String? = null,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        search()
    }

    fun onQueryChange(query: String) {
        _uiState.value = _uiState.value.copy(query = query)
    }

    fun onToggleTrueGem() {
        _uiState.value = _uiState.value.copy(
            filters = _uiState.value.filters.copy(trueGem = !_uiState.value.filters.trueGem)
        )
        search()
    }

    fun onToggleLocal() {
        _uiState.value = _uiState.value.copy(
            filters = _uiState.value.filters.copy(local = !_uiState.value.filters.local)
        )
        search()
    }

    fun search() {
        val current = _uiState.value
        viewModelScope.launch {
            _uiState.value = current.copy(loading = true, error = null, searched = true)
            when (val result = restaurantRepository.search(
                query = current.query,
                localOnly = current.filters.local,
                minOverall = current.filters.minOverall,
            )) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(loading = false, results = result.data)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        loading = false,
                        error = result.error,
                        errorDetail = result.detail,
                    )
            }
        }
    }
}
