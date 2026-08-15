package com.realmatjip.app.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.network.ApiError
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.RecentRestaurant
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.domain.repository.RecentRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val restaurantRepository: RestaurantRepository,
    recentRepository: RecentRepository,
) : ViewModel() {

    data class UiState(
        val loading: Boolean = true,
        val topRestaurants: List<Restaurant> = emptyList(),
        val localRestaurants: List<Restaurant> = emptyList(),
        val recents: List<RecentRestaurant> = emptyList(),
        val meta: BackendMeta? = null,
        val error: ApiError? = null,
        val errorDetail: String? = null,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            recentRepository.recents.collect { recents ->
                _uiState.value = _uiState.value.copy(recents = recents)
            }
        }
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(loading = true, error = null)
            val top = restaurantRepository.search(sort = "overall_a", limit = 5)
            val local = restaurantRepository.search(localOnly = true, limit = 5)
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
}
