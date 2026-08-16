package com.realmatjip.app.feature.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.width
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
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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

        // 기준 지역 설정 바 — 설정 후에만 그 지역 Top이 나온다
        val regionInput = remember { mutableStateOf("") }
        Column(Modifier.padding(horizontal = 16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = viewModel::useMyLocation, enabled = !state.locating) {
                    Text(if (state.locating) "찾는 중…" else "📍 내 위치")
                }
                OutlinedTextField(
                    value = regionInput.value,
                    onValueChange = { regionInput.value = it },
                    placeholder = { Text("지역명 (성남, 강남역…)") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { viewModel.searchRegion(regionInput.value) },
                    enabled = !state.locating && regionInput.value.isNotBlank(),
                ) { Text("검색") }
            }
            if (state.locating) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.padding(top = 6.dp),
                ) {
                    CircularProgressIndicator(Modifier.width(16.dp), strokeWidth = 2.dp)
                    Text("지역 확인 중…", style = MaterialTheme.typography.labelMedium)
                }
            }
            state.message?.let {
                Text(
                    it, style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            if (state.hasRegion) {
                Text(
                    "📍 ${state.regionLabel} 근처 기준",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 6.dp),
                )
            } else {
                Text(
                    "지역을 설정하면 그 지역의 찐맛집 Top을 보여줍니다",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 6.dp),
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
                    if (!state.hasRegion) {
                        item { EmptyView(text = "위에서 내 위치 또는 지역명 검색으로 지역을 정해주세요") }
                    } else {
                        item { EmptyView(text = "이 지역엔 아직 추가된 맛집이 없습니다.
검색/지도 탭에서 이 지역 맛집을 추가해 보세요") }
                    }
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
