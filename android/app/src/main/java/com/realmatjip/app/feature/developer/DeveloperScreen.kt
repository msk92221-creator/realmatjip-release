package com.realmatjip.app.feature.developer

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.core.ui.components.SectionHeader
import java.util.Locale

/** Developer (스펙 §10) — Import, LLM 분석, 재계산, 백업. 없는 기능은 Phase 3B/4 표기. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeveloperScreen(
    onBack: () -> Unit,
    viewModel: DeveloperViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val keyboard = LocalSoftwareKeyboardController.current
    val resolver = androidx.compose.ui.platform.LocalContext.current.contentResolver

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.runCatching {
            resolver.openInputStream(this)?.use { input ->
                input.readBytes().toString(Charsets.UTF_8)
            }
        }?.getOrNull()?.let { viewModel.onImportFile(it) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Developer") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "뒤로")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            BackendStatusCard(state, viewModel::testConnection)

            // ── 리뷰 Import (스펙 §10) ──────────────────────────
            SectionHeader("리뷰 Import (JSON / CSV)")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = state.importState.format == "json",
                    onClick = { viewModel.onImportFormatChange("json") },
                    label = { Text("JSON") },
                )
                FilterChip(
                    selected = state.importState.format == "csv",
                    onClick = { viewModel.onImportFormatChange("csv") },
                    label = { Text("CSV") },
                )
                OutlinedButton(onClick = { filePicker.launch(arrayOf("*/*")) }) {
                    Text("파일 열기")
                }
            }
            OutlinedTextField(
                value = state.importState.content,
                onValueChange = viewModel::onImportContentChange,
                modifier = Modifier.fillMaxWidth().height(140.dp),
                placeholder = { Text("{\"restaurants\": [{\"name\": ..., \"reviews\": [...]}]}") },
                textStyle = MaterialTheme.typography.bodySmall,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = viewModel::previewImport,
                    enabled = state.importState.canPreview,
                ) { Text("Import 미리보기") }
                Button(
                    onClick = viewModel::commitImport,
                    enabled = state.importState.canCommit,
                ) { Text("Import 실행") }
            }
            state.importState.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                     style = MaterialTheme.typography.labelMedium)
            }
            state.importState.preview?.let { preview ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text(
                            "신규 리뷰 ${preview.estimatedNewReviews} · 중복 ${preview.exactDuplicates} · " +
                                "오류 ${preview.invalid} (총 ${preview.total}행)",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Text(
                            "신규 식당 ${preview.newRestaurants} · 기존 매칭 ${preview.matchedRestaurants}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        preview.errors.take(5).forEach { error ->
                            Text(
                                "• ${error.row}행 [${error.field}] ${error.reason}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }
            state.importState.commit?.let { commit ->
                Card(Modifier.fillMaxWidth()) {
                    Text(
                        "Import 완료 — 식당 ${commit.insertedRestaurants}개 · 리뷰 ${commit.insertedReviews}개 " +
                            "· 중복 제외 ${commit.skippedDuplicates}",
                        Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            // ── LLM 분석 (스펙 §10) ────────────────────────────
            SectionHeader("LLM 리뷰 분석")
            state.analyzeState.estimate?.let { estimate ->
                Text(
                    "대상 ${estimate.toAnalyze}개 · 캐시 ${estimate.cachedHits}개 · " +
                        "예상 ${estimate.estimatedTokensInput + estimate.estimatedTokensOutput}토큰 " +
                        "($${String.format(Locale.US, "%.4f", estimate.estimatedCost)})",
                    style = MaterialTheme.typography.labelMedium,
                )
                Text(
                    "분석기 ${estimate.analyzer} · 프롬프트 ${estimate.promptVersion}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (!estimate.withinLimits) {
                    Text(
                        "예상 사용량이 상한 초과 — 실행이 차단됩니다",
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = viewModel::loadAnalyzeEstimate) { Text("사용량 조회") }
                Button(onClick = viewModel::analyzePending) { Text("미분석 리뷰 분석") }
            }
            state.analyzeState.job?.let { job ->
                AnalyzeJobProgress(job)
            }
            state.analyzeState.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                     style = MaterialTheme.typography.labelMedium)
            }

            // ── Google Places 검색 (Phase 3B, 스펙 §22) ────────
            SectionHeader("Google Places 검색")
            OutlinedTextField(
                value = state.googleState.query,
                onValueChange = viewModel::onGoogleQueryChange,
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("성수동 돈까스") },
                singleLine = true,
            )
            Button(
                onClick = {
                    keyboard?.hide() // 3B.1 UX: 결과가 필드 아래에 나오므로 키보드를 내린다
                    viewModel.searchGooglePlaces()
                },
                enabled = state.googleState.query.isNotBlank() && !state.googleState.searching,
            ) { Text(if (state.googleState.searching) "검색 중…" else "식당 검색") }

            state.googleState.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                     style = MaterialTheme.typography.labelMedium)
            }

            // 검색 결과
            state.googleState.results.forEach { place ->
                Card(
                    Modifier.fillMaxWidth().padding(vertical = 2.dp),
                ) {
                    Column(Modifier.padding(10.dp)) {
                        Text(place.name, style = MaterialTheme.typography.titleSmall,
                             fontWeight = FontWeight.Bold)
                        Text(place.formattedAddress,
                             style = MaterialTheme.typography.labelSmall,
                             color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            "★${place.rating ?: "-"} · 리뷰 ${place.userRatingCount}개",
                            style = MaterialTheme.typography.labelSmall,
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            OutlinedButton(
                                onClick = {
                                    keyboard?.hide()
                                    viewModel.googlePreview(place.placeId)
                                },
                                enabled = state.googleState.selectedPlaceId != place.placeId,
                            ) { Text("Preview") }
                        }
                    }
                }
            }

            // Preview 결과
            state.googleState.preview?.let { preview ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(preview.place.name, fontWeight = FontWeight.Bold)
                        if (preview.match.matchType != "no_match") {
                            Text(
                                "기존 식당 매칭: ${preview.match.matchedName} " +
                                    "(거리 ${preview.match.distanceM ?: "?"}m, ${preview.match.matchType})",
                                color = MaterialTheme.colorScheme.primary,
                            )
                        } else {
                            Text("기존 식당 매칭: 없음 (신규 생성)")
                        }
                        Text(
                            "Google ★${preview.place.rating ?: "-"} · 전체 ${preview.place.userRatingCount}개 · " +
                                "샘플 ${preview.reviewCount}개 · 신규 ${preview.newReviews} · 중복 ${preview.duplicates}",
                        )
                        preview.reviewSamples.take(3).forEach { sample ->
                            Text(
                                "  \"${sample.text.take(50)}…\" — ${sample.authorName} ★${sample.rating}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Button(
                                onClick = { viewModel.googleCommit(false) },
                                enabled = !state.googleState.committing,
                            ) { Text("Import") }
                            if (preview.match.matchType != "no_match") {
                                OutlinedButton(
                                    onClick = { viewModel.googleCommit(true) },
                                    enabled = !state.googleState.committing,
                                ) { Text("새 식당으로 추가") }
                            }
                        }
                    }
                }
            }

            state.googleState.commitResult?.let { commit ->
                Card(Modifier.fillMaxWidth()) {
                    Text(
                        "Import 완료 — ${commit.restaurantName} (${"linked" == commit.action}) " +
                            "· 리뷰 ${commit.insertedReviews}개 추가 (중복 ${commit.skippedDuplicates})",
                        Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }

            // ── 재계산 / 시드 / 백업 ────────────────────────────
            SectionHeader("데이터 작업")
            Button(onClick = viewModel::recalculate, modifier = Modifier.fillMaxWidth()) {
                Text("전체 점수 재계산")
            }
            state.job?.let { job ->
                Text(
                    "점수 다시 계산 중 ${job.done ?: 0} / ${job.total ?: 0} (${job.status})",
                    style = MaterialTheme.typography.labelMedium,
                )
                if (!job.isFinished && (job.total ?: 0) > 0) {
                    LinearProgressIndicator(
                        progress = { (job.done ?: 0).toFloat() / job.total!!.toFloat() },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { viewModel.seed(false) }) { Text("Fixture 시드") }
                OutlinedButton(onClick = { viewModel.seed(true) }) { Text("초기화 후 시드") }
            }
            Button(onClick = viewModel::backup, modifier = Modifier.fillMaxWidth()) {
                Text("DB Backup (Export)")
            }
            state.notice?.let {
                Text(it, style = MaterialTheme.typography.labelMedium,
                     color = MaterialTheme.colorScheme.primary)
            }
            state.jobError?.let {
                Text(it, color = MaterialTheme.colorScheme.error,
                     style = MaterialTheme.typography.labelMedium)
            }

            SectionHeader("연결 / 업데이트")
            Button(onClick = viewModel::testConnection, modifier = Modifier.fillMaxWidth()) {
                Text("API 연결 테스트")
            }
            TextButton(onClick = {}, enabled = false) {
                Text("리뷰 업데이트(자동 수집) — Phase 3B", fontWeight = FontWeight.Normal)
            }
            TextButton(
                onClick = viewModel::forceUpdateCheck,
                enabled = !state.updateChecking,
            ) {
                Text(
                    if (state.updateChecking) "업데이트 확인 중…"
                    else "GitHub 업데이트 강제 확인",
                    fontWeight = FontWeight.Normal,
                )
            }
            state.updateCheck?.let {
                Text(it, style = MaterialTheme.typography.labelMedium)
            }
            TextButton(onClick = viewModel::refresh) { Text("새로고침") }
        }
    }
}

@Composable
private fun BackendStatusCard(
    state: DeveloperViewModel.UiState,
    onTest: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            when {
                state.backendStatus != null -> Text(
                    "연결됨 — ${state.backendStatus}",
                    color = MaterialTheme.colorScheme.primary,
                )
                state.backendError != null -> Text(
                    state.backendError,
                    color = MaterialTheme.colorScheme.error,
                )
                else -> Text("확인 중…")
            }
            state.meta?.let { meta ->
                Text("알고리즘: ${meta.algorithmVersion}")
                Text("분석기: ${meta.analyzer ?: "-"} / 프롬프트: ${meta.promptVersion ?: "-"}")
            }
            state.stats?.let { stats ->
                Text(
                    "식당 ${stats.restaurants} · 리뷰 ${stats.reviews} · " +
                        "분석 완료 ${stats.analyzed} · 미분석 ${stats.unanalyzed}",
                )
                Text("중복 감지 ${stats.duplicateFlagged} · 수동 라벨 ${stats.manualLabels}")
            }
            OutlinedButton(onClick = onTest) { Text("연결 테스트") }
        }
    }
}

@Composable
private fun AnalyzeJobProgress(job: com.realmatjip.app.domain.model.JobInfo) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                when {
                    job.status == "done" -> "분석 완료"
                    job.status == "failed" -> "분석 실패: ${job.error ?: ""}"
                    else -> "분석 중… ${job.completed ?: 0}/${job.pendingTotalOf()}"
                },
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
            )
            job.model?.let { Text("모델 $it · 프롬프트 ${job.promptVersion ?: "-"}") }
            Text(
                "완료 ${job.completed ?: 0} · 캐시 ${job.cached ?: 0} · 실패 ${job.failed ?: 0}",
                style = MaterialTheme.typography.labelMedium,
            )
            if (job.tokensInput != null || job.tokensOutput != null) {
                Text(
                    "토큰 in ${job.tokensInput ?: 0} / out ${job.tokensOutput ?: 0}" +
                        (job.estimatedCost?.let {
                            " · $" + String.format(Locale.US, "%.4f", it)
                        } ?: ""),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (!job.isFinished) {
                val total = (job.pendingTotalOf()).takeIf { it > 0 }
                if (total != null) {
                    LinearProgressIndicator(
                        progress = { (job.completed ?: 0).toFloat() / total },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

private fun com.realmatjip.app.domain.model.JobInfo.pendingTotalOf(): Int =
    (total ?: ((completed ?: 0) + (cached ?: 0) + (failed ?: 0)))
