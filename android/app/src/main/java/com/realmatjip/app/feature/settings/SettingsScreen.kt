package com.realmatjip.app.feature.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.BuildConfig
import com.realmatjip.app.core.ui.components.SectionHeader
import com.realmatjip.app.domain.model.AdFilter

/** 설정 (스펙 §22) — Backend URL/Token은 여기서만 관리, APK에 고정값 없음. */
@Composable
fun SettingsScreen(
    onOpenDeveloper: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val test by viewModel.connectionTest.collectAsState()
    val updateViewModel: com.realmatjip.app.feature.update.UpdateViewModel = hiltViewModel()
    val update by updateViewModel.uiState.collectAsState()

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        SectionHeader("Backend")
        OutlinedTextField(
            value = state.backendUrl,
            onValueChange = viewModel::onUrlChange,
            label = { Text("Backend URL (Tailscale/LAN)") },
            placeholder = { Text("http://100.x.x.x:8000") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        OutlinedTextField(
            value = state.apiToken,
            onValueChange = viewModel::onTokenChange,
            label = { Text("API Token (선택)") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = viewModel::saveConnection) { Text("저장") }
            Button(onClick = viewModel::testConnection) { Text("연결 테스트") }
        }
        when {
            test.running -> Text("연결 확인 중…", style = MaterialTheme.typography.labelMedium)
            test.success != null -> Text(
                test.success!!,
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelMedium,
            )
            test.failure != null -> Text(
                test.failure!!,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.labelMedium,
            )
        }

        SectionHeader("리뷰 필터")
        Text(
            "기본 광고 필터 — 리뷰 목록에 적용되는 기준",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            AdFilter.entries.forEach { filter ->
                FilterChip(
                    selected = state.defaultAdFilter == filter,
                    onClick = { viewModel.setDefaultAdFilter(filter) },
                    label = { Text(filter.label) },
                )
            }
        }

        SectionHeader("앱")
        Text("현재 버전 v${BuildConfig.VERSION_NAME}",
             style = MaterialTheme.typography.bodyMedium)
        Button(
            onClick = updateViewModel::checkNow,
            enabled = !update.checking && !update.downloading,
        ) {
            Text(if (update.checking) "확인 중…" else "업데이트 확인")
        }
        when {
            update.upToDate -> Text(
                "최신 버전입니다",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            update.message != null -> Text(
                "업데이트 확인 실패: ${update.message} (앱 사용에는 문제없음)",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
        if (update.showDialog) {
            com.realmatjip.app.feature.update.UpdateDialog(
                state = update,
                onDownload = updateViewModel::downloadAndInstall,
                onInstallRetry = updateViewModel::retryInstall,
                onDismiss = updateViewModel::dismiss,
            )
        }

        SectionHeader("개발자")
        SettingSwitch(
            label = "Developer Mode",
            checked = state.developerMode,
            onChange = viewModel::setDeveloperMode,
        )
        if (state.developerMode) {
            Button(onClick = onOpenDeveloper) { Text("Developer 화면 열기") }
        }
    }
}

@Composable
private fun SettingSwitch(
    label: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
