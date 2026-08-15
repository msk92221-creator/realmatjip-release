package com.realmatjip.app.feature.update

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** Phase 4 업데이트 다이얼로그 (스펙 §10) — 홈/설정 공용. */
@Composable
fun UpdateDialog(
    state: UpdateViewModel.UiState,
    onDownload: () -> Unit,
    onInstallRetry: () -> Unit,
    onDismiss: () -> Unit,
) {
    val update = state.available ?: return
    AlertDialog(
        onDismissRequest = { if (!update.mandatory) onDismiss() },
        title = { Text(if (update.mandatory) "필수 업데이트" else "업데이트 v${update.version}") },
        text = {
            Column {
                if (update.notes.isNotBlank()) {
                    Text(
                        update.notes.take(400),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 8,
                    )
                }
                if (state.downloading) {
                    val total = state.totalBytes.coerceAtLeast(1)
                    LinearProgressIndicator(
                        progress = { (state.progressBytes.toFloat() / total).coerceIn(0f, 1f) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 12.dp),
                    )
                    Text(
                        "${state.progressBytes / 1_000_000} / ${state.totalBytes / 1_000_000} MB",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                if (state.installLaunched) {
                    Text(
                        "설치 화면을 열었습니다 — 설치를 진행해 주세요.",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.Medium,
                    )
                }
                if (state.installFailed) {
                    Text(
                        "설치 화면 실행 실패 — 다시 시도해 주세요",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                val failure = state.message
                if (failure != null && !state.downloading) {
                    Text(
                        failure,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            when {
                state.installLaunched -> TextButton(onClick = onDismiss) { Text("닫기") }
                state.downloadedFile != null -> TextButton(onClick = onInstallRetry) { Text("설치 다시 열기") }
                state.downloading -> {}
                else -> TextButton(onClick = onDownload) {
                    Text(if (update.mandatory) "지금 업데이트" else "다운로드")
                }
            }
        },
        dismissButton = {
            // 최소 버전 미만(mandatory)도 설치는 사용자 동의 — 나중에 닫기만 제한한다.
            if (!update.mandatory && !state.downloading) {
                TextButton(onClick = onDismiss) { Text("나중에") }
            }
        },
    )
}
