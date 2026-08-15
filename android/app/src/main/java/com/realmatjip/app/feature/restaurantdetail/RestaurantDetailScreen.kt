package com.realmatjip.app.feature.restaurantdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.core.common.Formatters
import com.realmatjip.app.core.common.evidenceLabel
import com.realmatjip.app.core.network.userMessage
import com.realmatjip.app.core.ui.components.ErrorView
import com.realmatjip.app.core.ui.components.LoadingView
import com.realmatjip.app.core.ui.components.ScoreBadge
import com.realmatjip.app.core.ui.components.SectionHeader
import com.realmatjip.app.domain.model.AdFilter
import com.realmatjip.app.domain.model.RestaurantDetail
import com.realmatjip.app.domain.model.ReviewItem
import com.realmatjip.app.domain.model.SubScores

/** 상세 (스펙 §9~§13) — Header → Overall → Evidence → Sub Scores → Explanation
 * → Platform Stats → Reviews(광고 필터 + 개발자 모드 수동 라벨 + 재계산 진행률). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RestaurantDetailScreen(
    restaurantId: String,
    onBack: () -> Unit,
    viewModel: RestaurantDetailViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.detail?.name ?: "상세") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "뒤로")
                    }
                },
                actions = {
                    IconButton(onClick = viewModel::toggleFavorite) {
                        Icon(
                            if (state.isFavorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                            contentDescription = "즐겨찾기",
                        )
                    }
                },
            )
        },
    ) { padding ->
        when {
            state.detailLoading && state.detail == null -> LoadingView(Modifier.padding(padding))
            state.detailError != null && state.detail == null -> ErrorView(
                error = state.detailError!!,
                detail = state.detailErrorDetail,
                onRetry = viewModel::load,
                modifier = Modifier.padding(padding),
            )
            state.detail == null -> LoadingView(Modifier.padding(padding))
            else -> DetailContent(
                state = state,
                onFilter = viewModel::setAdFilter,
                onLabel = viewModel::setManualLabel,
                onRecalculate = viewModel::recalculate,
                modifier = Modifier.padding(padding),
            )
        }
    }
}

@Composable
private fun DetailContent(
    state: RestaurantDetailViewModel.UiState,
    onFilter: (AdFilter) -> Unit,
    onLabel: (String, String?) -> Unit,
    onRecalculate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val detail = state.detail ?: return

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item(key = "header") { DetailHeader(detail) }
        item(key = "overall") { OverallSection(detail) }
        if (detail.signals != null) item(key = "evidence") { EvidenceSection(detail) }
        if (detail.subscores != null) item(key = "subscores") { SubScoresSection(detail.subscores!!) }
        if (detail.explanation.isNotEmpty()) item(key = "explanation") { ExplanationSection(detail) }
        if (detail.platforms.isNotEmpty()) item(key = "platforms") { PlatformSection(detail) }

        item(key = "reviews-header") {
            ReviewsHeader(state = state, onFilter = onFilter, onRecalculate = onRecalculate)
        }
        when {
            state.reviewsLoading -> item(key = "reviews-loading") {
                Text("리뷰 불러오는 중…", modifier = Modifier.padding(8.dp))
            }
            state.reviewsError != null -> item(key = "reviews-error") {
                TextButton(onClick = { onFilter(state.adFilter) }) {
                    Text("${state.reviewsError!!.userMessage()} — 다시 시도")
                }
            }
            state.reviews != null -> {
                if (state.reviews!!.items.isEmpty()) {
                    item(key = "reviews-empty") {
                        Text(
                            "이 필터에서 표시할 리뷰가 없습니다",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(8.dp),
                        )
                    }
                } else {
                    items(state.reviews!!.items, key = { it.id }) { review ->
                        ReviewCard(
                            review = review,
                            developerMode = state.developerMode,
                            onLabel = onLabel,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailHeader(detail: RestaurantDetail) {
    Column {
        if (detail.fromCache) {
            Card(Modifier.fillMaxWidth()) {
                Text(
                    "이전 데이터 — 오프라인 캐시" +
                        (detail.cacheAgeHours?.let { " (${it}시간 전)" } ?: ""),
                    Modifier.padding(10.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }
            Spacer(Modifier.height(8.dp))
        }
        Text(detail.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        if (detail.category.isNotBlank() || detail.address.isNotBlank()) {
            Text(
                listOf(detail.category, detail.address).filter { it.isNotBlank() }.joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (detail.message != null) {
            Text(
                detail.message!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun OverallSection(detail: RestaurantDetail) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth(),
    ) {
        ScoreBadge(score = detail.primaryScore, size = 96.dp)
        Spacer(Modifier.width(16.dp))
        Column {
            Text("종합 점수", style = MaterialTheme.typography.labelMedium)
            Text(
                Formatters.score(detail.overallA),
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                "재계산 가중치(B) ${Formatters.score(detail.overallB)}" +
                    (detail.calculatedAt?.let { " · 계산 $it" } ?: ""),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun EvidenceSection(detail: RestaurantDetail) {
    val signals = detail.signals ?: return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("근거 강도", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(
                evidenceLabel(signals.evidenceStrength),
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                "유효 리뷰 근거 ${Formatters.effReviews(signals.nEff)} · 원본 리뷰 ${signals.nRaw}개" +
                    (if (signals.localBadge) " · 로컬맛집 배지" else ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun SubScoresSection(subscores: SubScores) {
    Column {
        SectionHeader("하위 점수")
        val rows = listOf(
            listOf("보정평점" to subscores.ratingAdjusted, "로컬" to subscores.local),
            listOf("신뢰도" to subscores.trust, "광고청정" to subscores.adFree),
            listOf("음식" to subscores.food, "가성비" to subscores.value),
        )
        rows.forEach { row ->
            Row(Modifier.fillMaxWidth().padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (label, value) ->
                    Card(Modifier.weight(1f)) {
                        Column(Modifier.padding(12.dp)) {
                            Text(label, style = MaterialTheme.typography.labelSmall)
                            Text(
                                Formatters.subScore(value),
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun ExplanationSection(detail: RestaurantDetail) {
    Column {
        SectionHeader("왜 이 점수인가")
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                detail.explanation.forEach { item ->
                    val positive = item.points >= 0
                    Row {
                        Text(
                            if (positive) "✓" else "△",
                            color = if (positive) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.tertiary,
                            fontWeight = FontWeight.Bold,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "${item.label} ${Formatters.score(item.points)}점",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun PlatformSection(detail: RestaurantDetail) {
    Column {
        SectionHeader("플랫폼별 평가")
        detail.platforms.forEach { platform ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(platform.source, style = MaterialTheme.typography.bodyMedium)
                Text(
                    "${Formatters.stars(platform.shrunkRating * 4 + 1)} (${platform.nReviews}개)",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ReviewsHeader(
    state: RestaurantDetailViewModel.UiState,
    onFilter: (AdFilter) -> Unit,
    onRecalculate: () -> Unit,
) {
    Column {
        SectionHeader("리뷰")
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            AdFilter.entries.forEach { filter ->
                FilterChip(
                    selected = state.adFilter == filter,
                    onClick = { onFilter(filter) },
                    label = { Text(filter.label) },
                )
            }
        }
        state.reviews?.threshold?.let {
            Text(
                "광고 가능성 ${Formatters.percent(it)} 미만 표시 · " +
                    "전체 ${state.reviews!!.total}개 중 ${state.reviews!!.returned}개",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
        }

        if (state.developerMode) {
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = onRecalculate) { Text("점수 다시 계산") }
            state.job?.let { job ->
                Text(
                    when {
                        job.isFinished && job.status == "done" -> "재계산 완료 (${job.done ?: 0}/${job.total ?: 0})"
                        job.status == "failed" -> "재계산 실패: ${job.error ?: ""}"
                        else -> "점수 다시 계산 중 ${job.done ?: 0} / ${job.total ?: 0}"
                    },
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(top = 4.dp),
                )
                if (!job.isFinished && (job.total ?: 0) > 0) {
                    LinearProgressIndicator(
                        progress = { (job.done ?: 0).toFloat() / job.total!!.toFloat() },
                        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                    )
                }
            }
            state.jobError?.let {
                Text(
                    "오류: $it",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

@Composable
private fun ReviewCard(
    review: ReviewItem,
    developerMode: Boolean,
    onLabel: (String, String?) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(Formatters.stars(review.rating), style = MaterialTheme.typography.labelMedium)
                Text(
                    review.source,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(review.text, style = MaterialTheme.typography.bodyMedium)
            review.analysis?.let { analysis ->
                Spacer(Modifier.height(2.dp))
                MetricRow("광고 가능성", Formatters.percent(analysis.adProbability))
                MetricRow("리뷰 신뢰도", Formatters.percent(analysis.authenticity))
                MetricRow("로컬 가능성", Formatters.percent(analysis.localProbability))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (analysis.repeatVisit == true) {
                        Text("재방문", style = MaterialTheme.typography.labelSmall)
                    }
                    if (analysis.negativePoints == true) {
                        Text("단점 언급", style = MaterialTheme.typography.labelSmall)
                    }
                    if (analysis.specificity >= 0.7) {
                        Text("구체적 메뉴 평가", style = MaterialTheme.typography.labelSmall)
                    }
                }
                if (review.duplicateOf != null) {
                    Text(
                        "유사 문구 반복 감지",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.tertiary,
                    )
                }
            }
            review.manualLabel?.let { label ->
                Text(
                    "수동 판정: ${manualLabelDisplay(label)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            if (developerMode) {
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(onClick = { onLabel(review.id, "normal") }) { Text("일반 리뷰") }
                    TextButton(onClick = { onLabel(review.id, "ad_likely") }) { Text("광고 가능성 높음") }
                    TextButton(onClick = { onLabel(review.id, "ambiguous") }) { Text("판단 어려움") }
                    TextButton(onClick = { onLabel(review.id, null) }) { Text("제거") }
                }
            }
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.labelSmall)
    }
}

private fun manualLabelDisplay(label: String): String = when (label) {
    "ad" -> "광고로 확정"
    "ad_likely" -> "광고 가능성 높음"
    "ambiguous" -> "판단 어려움"
    "normal" -> "일반 리뷰"
    else -> label
}
