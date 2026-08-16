package com.realmatjip.app.feature.map

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.MarkerComposable
import com.google.maps.android.compose.rememberCameraPositionState
import com.google.maps.android.compose.rememberMarkerState
import com.google.android.gms.maps.CameraUpdateFactory
import com.realmatjip.app.core.common.Formatters
import com.realmatjip.app.core.ui.components.scoreColor
import com.realmatjip.app.domain.model.Restaurant
import com.realmatjip.app.feature.search.NearbyPlaceRow
import com.realmatjip.app.feature.search.NearbyViewModel
import com.realmatjip.app.feature.search.phaseLabel

/** 지도 화면 — 별점이 아니라 자체 점수를 마커로 표시 (스펙 §15). */
@Composable
fun MapScreen(
    onRestaurantClick: (String) -> Unit,
    viewModel: MapViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val nearbyViewModel: NearbyViewModel = hiltViewModel()
    val nearby by nearbyViewModel.uiState.collectAsState()
    val cameraTarget by viewModel.cameraTarget.collectAsState()
    val locationFailed by viewModel.locationFailed.collectAsState()

    if (!state.hasMapsKey) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "지도를 사용하려면 Google Maps API 키가 필요합니다",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                "android/local.properties에 MAPS_API_KEY를 설정하고 다시 빌드하세요.\n" +
                    "(콘솔에서 패키지 com.realmatjip.app + 서명 지정 제한 권장)",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        return
    }

    val seoul = remember { LatLng(37.5514, 127.0) }
    val cameraState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(seoul, 11f)
    }

    Box(Modifier.fillMaxSize()) {
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = cameraState,
            onMapLoaded = {
                cameraState.projection?.visibleRegion?.latLngBounds?.let { bounds ->
                    viewModel.onCameraIdle(
                        bounds.southwest.latitude, bounds.southwest.longitude,
                        bounds.northeast.latitude, bounds.northeast.longitude,
                    )
                }
            },
        ) {
            state.restaurants.forEach { restaurant ->
                val markerState = rememberMarkerState(
                    key = restaurant.id,
                    position = LatLng(restaurant.lat, restaurant.lng),
                )
                MarkerComposable(
                    keys = arrayOf(restaurant.id),
                    state = markerState,
                    onClick = {
                        viewModel.select(restaurant.id)
                        true
                    },
                ) {
                    ScoreMarker(restaurant.primaryScore)
                }
            }
        }

        if (state.loading) {
            Text(
                "현재 영역 검색 중…",
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(12.dp)
                    .background(MaterialTheme.colorScheme.surface)
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                style = MaterialTheme.typography.labelMedium,
            )
        }

        // 우측: 내 위치 버튼
        SmallFloatingActionButton(
            onClick = viewModel::moveToMyLocation,
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .padding(end = 12.dp),
        ) { Text("📍", fontSize = 20.sp) }

        // 하단: 이 위치 맛집 찾기 — 지도 중심 좌표로 요청 시 검색 (미리 계산 아님)
        ExtendedFloatingActionButton(
            onClick = {
                val center = cameraState.position.target
                nearbyViewModel.exploreAt(center.latitude, center.longitude)
            },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 12.dp),
        ) { Text(if (nearby.working) phaseLabel(nearby.phase) else "🔍 이 위치 맛집 찾기") }

        if (locationFailed) {
            Text(
                "위치를 가져올 수 없어요 — GPS 켜고 다시 눌러주세요",
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 48.dp)
                    .background(MaterialTheme.colorScheme.errorContainer)
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onErrorContainer,
            )
        }

        // 주변 탐색 상태 패널 — 진행바 / 결과 / 완료
        when {
            nearby.working -> Card(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(bottom = 72.dp, start = 12.dp, end = 12.dp),
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(phaseLabel(nearby.phase), style = MaterialTheme.typography.labelMedium)
                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                }
            }

            nearby.phase == NearbyViewModel.Phase.Results -> Card(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(bottom = 72.dp, start = 12.dp, end = 12.dp),
            ) {
                Column(
                    Modifier
                        .padding(12.dp)
                        .heightIn(max = 280.dp)
                        .verticalScroll(rememberScrollState()),
                ) {
                    Text(
                        "이 위치 근처 " + nearby.results.size + "곳 — 추가하면 분석·점수 계산까지 자동",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    nearby.results.forEach { place ->
                        NearbyPlaceRow(place, nearby.myLat, nearby.myLng, nearbyViewModel)
                    }
                    Button(
                        onClick = nearbyViewModel::importAllAndFinalize,
                        modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
                    ) { Text("전체 추가 (" + nearby.results.size + "곳)") }
                }
            }

            nearby.phase == NearbyViewModel.Phase.Done -> Card(
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 72.dp),
            ) {
                Text(
                    nearby.message ?: "완료",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }

        state.restaurants.firstOrNull { it.id == state.selectedId }?.let { selected ->
            Card(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(12.dp)
                    .clickable { onRestaurantClick(selected.id) },
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(selected.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        "Overall ${Formatters.score(selected.overallA)} · " +
                            "재계산(B) ${Formatters.score(selected.overallB)} · 리뷰 ${selected.nRaw}개",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(
                        onClick = { onRestaurantClick(selected.id) },
                        modifier = Modifier.padding(top = 8.dp),
                    ) { Text("상세보기") }
                }
            }
        }
    }

    LaunchedEffect(cameraTarget) {
        cameraTarget?.let { target ->
            cameraState.animate(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(target.first, target.second), 15f),
                800,
            )
        }
    }

    // 주변 임포트 파이프라인 완료 → 마커 새로고침
    LaunchedEffect(nearby.phase) {
        if (nearby.phase == NearbyViewModel.Phase.Done) viewModel.refresh()
    }

    LaunchedEffect(cameraState.isMoving) {
        if (!cameraState.isMoving) {
            cameraState.projection?.visibleRegion?.latLngBounds?.let { bounds ->
                viewModel.onCameraIdle(
                    bounds.southwest.latitude, bounds.southwest.longitude,
                    bounds.northeast.latitude, bounds.northeast.longitude,
                )
            }
        }
    }
}

@Composable
private fun ScoreMarker(score: Double?) {
    Box(
        modifier = Modifier
            .size(40.dp)
            .background(scoreColor(score), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            Formatters.scoreInt(score),
            color = Color.White,
            fontSize = 14.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}
