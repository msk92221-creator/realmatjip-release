package com.realmatjip.app.feature.search

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.core.ui.components.EmptyView
import com.realmatjip.app.core.ui.components.ErrorView
import com.realmatjip.app.core.ui.components.LoadingView
import com.realmatjip.app.core.ui.components.RestaurantCard

/** 검색 — 자연어→필터 변환 LLM은 Phase 3 (스펙 §14). */
@Composable
fun SearchScreen(
    onRestaurantClick: (String) -> Unit,
    viewModel: SearchViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        OutlinedTextField(
            value = state.query,
            onValueChange = viewModel::onQueryChange,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("성수동, 냉면, 국밥…") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { viewModel.search() }),
        )
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(vertical = 8.dp),
        ) {
            FilterChip(
                selected = state.filters.trueGem,
                onClick = viewModel::onToggleTrueGem,
                label = { Text("찐맛집") },
            )
            FilterChip(
                selected = state.filters.local,
                onClick = viewModel::onToggleLocal,
                label = { Text("로컬") },
            )
            FilterChip(selected = false, onClick = {}, enabled = false, label = { Text("광고 적은 리뷰 (Phase 3)") })
            FilterChip(selected = false, onClick = {}, enabled = false, label = { Text("가성비 (Phase 3)") })
        }

        when {
            state.loading -> LoadingView()
            state.error != null -> ErrorView(
                error = state.error!!,
                detail = state.errorDetail,
                onRetry = viewModel::search,
            )
            state.results.isEmpty() -> EmptyView(
                text = if (state.searched) "검색 결과가 없습니다" else "검색어를 입력하세요"
            )
            else -> LazyColumn(
                contentPadding = PaddingValues(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item {
                    Text(
                        "결과 ${state.results.size}개",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                items(state.results, key = { it.id }) { restaurant ->
                    RestaurantCard(restaurant, onRestaurantClick)
                }
            }
        }
    }
}
