package com.realmatjip.app.feature.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.core.common.Formatters
import com.realmatjip.app.core.ui.components.EmptyView
import com.realmatjip.app.core.ui.components.ErrorView
import com.realmatjip.app.core.ui.components.LoadingView
import com.realmatjip.app.core.ui.components.RestaurantCard
import com.realmatjip.app.core.ui.components.ScoreBadge
import com.realmatjip.app.core.ui.components.SectionHeader

/** 홈 — 찐맛집 Top / 로컬맛집 Top / 최근 본 맛집 / 데이터 상태 (스펙 §7). */
@Composable
fun HomeScreen(
    onRestaurantClick: (String) -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    // Phase 4: 시작 시 자동 업데이트 확인 (24h 스로틀 — Throttled는 조용히 무시, 스펙 §10)
    val updateViewModel: com.realmatjip.app.feature.update.UpdateViewModel = hiltViewModel()
    val update by updateViewModel.uiState.collectAsState()
    LaunchedEffect(Unit) { updateViewModel.autoCheck() }
    if (update.showDialog) {
        com.realmatjip.app.feature.update.UpdateDialog(
            state = update,
            onDownload = updateViewModel::downloadAndInstall,
            onInstallRetry = updateViewModel::retryInstall,
            onDismiss = updateViewModel::dismiss,
        )
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Text("찐맛집", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(
                "광고보다 실제 경험을 봅니다",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            state.meta?.let { meta ->
                Spacer(Modifier.height(4.dp))
                Text(
                    "알고리즘 ${meta.algorithmVersion}" +
                        (meta.promptVersion?.let { " · 프롬프트 $it" } ?: ""),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        when {
            state.loading -> LoadingView()
            state.error != null -> ErrorView(
                error = state.error!!,
                detail = state.errorDetail,
                onRetry = viewModel::refresh,
            )
            else -> LazyColumn(
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (state.topRestaurants.isEmpty()) {
                    item { EmptyView(text = "아직 점수가 계산된 식당이 없습니다.\nDeveloper 화면에서 점수 재계산을 실행하세요") }
                } else {
                    item { SectionHeader("찐맛집 Top") }
                    items(state.topRestaurants, key = { it.id }) { restaurant ->
                        RestaurantCard(restaurant, onRestaurantClick)
                    }
                }
                if (state.localRestaurants.isNotEmpty()) {
                    item { SectionHeader("로컬맛집 Top") }
                    items(state.localRestaurants, key = { "local-" + it.id }) { restaurant ->
                        RestaurantCard(restaurant, onRestaurantClick)
                    }
                }
                if (state.recents.isNotEmpty()) {
                    item { SectionHeader("최근 본 맛집") }
                    items(state.recents, key = { "recent-" + it.id }) { recent ->
                        RecentRow(recent, onRestaurantClick)
                    }
                }
            }
        }
    }
}

@Composable
private fun RecentRow(
    recent: com.realmatjip.app.domain.model.RecentRestaurant,
    onRestaurantClick: (String) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        TextButton(onClick = { onRestaurantClick(recent.id) }) {
            Text(recent.name, style = MaterialTheme.typography.bodyLarge)
        }
        Text(
            Formatters.score(recent.overallScoreSnapshot),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.primary,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 10.dp),
        )
    }
}
