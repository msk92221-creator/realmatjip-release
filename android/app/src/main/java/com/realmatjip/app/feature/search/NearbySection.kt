package com.realmatjip.app.feature.search

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.domain.model.GooglePlace
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/** 주변 탐색 섹션 — 위치 권한 → 현재 위치 반경 맛집 → 임포트 → 분석/재계산 자동. */
@Composable
fun NearbySection(viewModel: NearbyViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { grants ->
        if (grants.values.any { it }) viewModel.explore()
        else viewModel.reset()
    }

    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("주변 탐색", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)

            when {
                state.working -> Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CircularProgressIndicator(Modifier.padding(2.dp), strokeWidth = 2.dp)
                    Text(phaseLabel(state.phase), style = MaterialTheme.typography.bodySmall)
                }

                state.phase == NearbyViewModel.Phase.Results -> {
                    Text(
                        "이 근처 ${state.results.size}곳을 찾았어요 — 추가하면 분석·점수 계산까지 자동으로 돼요",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    state.results.take(10).forEach { place ->
                        NearbyPlaceRow(place, state.myLat, state.myLng, viewModel)
                    }
                    if (state.results.isNotEmpty()) {
                        Button(onClick = viewModel::importAllAndFinalize, modifier = Modifier.fillMaxWidth()) {
                            Text("전체 추가 (${state.results.size}곳)")
                        }
                    }
                }

                state.phase == NearbyViewModel.Phase.Done ->
                    Text(
                        state.message ?: "완료",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )

                state.phase == NearbyViewModel.Phase.Failed -> {
                    Text(
                        state.message ?: "실패",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                    OutlinedButton(onClick = viewModel::explore) { Text("다시 시도") }
                }

                else -> {
                    Text(
                        "지금 서 있는 곳 근처의 맛집을 찾아올려요",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(onClick = {
                        val fine = ContextCompat.checkSelfPermission(
                            context, Manifest.permission.ACCESS_FINE_LOCATION,
                        ) == PackageManager.PERMISSION_GRANTED
                        val coarse = ContextCompat.checkSelfPermission(
                            context, Manifest.permission.ACCESS_COARSE_LOCATION,
                        ) == PackageManager.PERMISSION_GRANTED
                        if (fine || coarse) viewModel.explore()
                        else permissionLauncher.launch(
                            arrayOf(
                                Manifest.permission.ACCESS_FINE_LOCATION,
                                Manifest.permission.ACCESS_COARSE_LOCATION,
                            ),
                        )
                    }, modifier = Modifier.fillMaxWidth()) {
                        Text("📍 내 주변 맛집 찾기")
                    }
                }
            }

            if (state.phase == NearbyViewModel.Phase.Results && state.importedCount > 0) {
                Text(
                    "지금까지 ${state.importedCount}곳 추가됨",
                    style = MaterialTheme.typography.labelSmall,
                )
                TextButton(onClick = viewModel::finalize) { Text("분석·점수 계산 실행") }
            }
        }
    }
}

@Composable
internal fun NearbyPlaceRow(
    place: GooglePlace,
    myLat: Double?,
    myLng: Double?,
    viewModel: NearbyViewModel,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(place.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            Text(
                buildString {
                    append("★${place.rating ?: "-"} · 리뷰 ${place.userRatingCount}개")
                    distanceMeters(myLat, myLng, place.lat, place.lng)?.let { append(" · ${it}m") }
                },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        OutlinedButton(onClick = { viewModel.importPlace(place) }) { Text("추가") }
    }
}

private fun distanceMeters(lat1: Double?, lng1: Double?, lat2: Double, lng2: Double): Int? {
    if (lat1 == null || lng1 == null) return null
    val r = 6_371_000.0
    val dLat = Math.toRadians(lat2 - lat1)
    val dLng = Math.toRadians(lng2 - lng1)
    val a = sin(dLat / 2) * sin(dLat / 2) +
        cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLng / 2) * sin(dLng / 2)
    return (r * 2 * atan2(sqrt(a), sqrt(1 - a))).toInt()
}

internal fun phaseLabel(phase: NearbyViewModel.Phase): String = when (phase) {
    NearbyViewModel.Phase.Locating -> "위치 확인 중…"
    NearbyViewModel.Phase.Searching -> "주변 맛집 검색 중…"
    NearbyViewModel.Phase.Importing -> "식당 추가 중…"
    NearbyViewModel.Phase.Analyzing -> "리뷰 LLM 분석 중… (리뷰 수에 따라 1~3분)"
    NearbyViewModel.Phase.Recalculating -> "점수 계산 중…"
    else -> "처리 중…"
}
