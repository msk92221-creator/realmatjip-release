package com.realmatjip.app.feature.update

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.update.ApkInstaller
import com.realmatjip.app.data.update.DownloadEvent
import com.realmatjip.app.data.update.UpdateRepository
import com.realmatjip.app.data.update.UpdateState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * Phase 4 업데이트 UI 상태 (스펙 §10 — 사용자 동의 설치만, 실패해도 앱 사용 가능).
 * 홈(자동 확인, 24h 스로틀)과 설정(수동 확인)이 각각 인스턴스를 갖는다.
 */
@HiltViewModel
class UpdateViewModel @Inject constructor(
    private val updateRepository: UpdateRepository,
    private val apkInstaller: ApkInstaller,
) : ViewModel() {

    data class UiState(
        val checking: Boolean = false,
        val available: UpdateState.Available? = null,
        val upToDate: Boolean = false,
        val message: String? = null,
        val downloading: Boolean = false,
        val progressBytes: Long = 0,
        val totalBytes: Long = 0,
        val downloadedFile: File? = null,
        val installLaunched: Boolean = false,
        val installFailed: Boolean = false,
        /** 다이얼로그 표시 여부 — 자동 확인에서 Available 발견 시 true. */
        val showDialog: Boolean = false,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    /** 앱 시작 자동 확인 — 스로틀 적용 (24h 내 재확인 없음, Throttled는 조용히 무시). */
    fun autoCheck() {
        viewModelScope.launch {
            val state = updateRepository.checkForUpdate(force = false)
            if (state is UpdateState.Available) {
                _uiState.value = UiState(available = state, showDialog = true)
            }
        }
    }

    /** 사용자 요청 확인 — 스로틀 무시. */
    fun checkNow() {
        viewModelScope.launch {
            _uiState.value = UiState(checking = true)
            _uiState.value = when (val state = updateRepository.checkForUpdate(force = true)) {
                is UpdateState.Available -> UiState(available = state, showDialog = true)
                is UpdateState.UpToDate -> UiState(upToDate = true)
                is UpdateState.Throttled -> UiState(upToDate = true)
                is UpdateState.Unavailable -> UiState(message = state.reason)
            }
        }
    }

    fun dismiss() {
        _uiState.value = _uiState.value.copy(showDialog = false)
    }

    fun downloadAndInstall() {
        val update = _uiState.value.available ?: return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                downloading = true, progressBytes = 0, totalBytes = update.apkSizeBytes,
            )
            updateRepository.downloadApk(update).collect { event ->
                when (event) {
                    is DownloadEvent.Progress ->
                        _uiState.value = _uiState.value.copy(
                            progressBytes = event.bytes, totalBytes = event.totalBytes,
                        )
                    is DownloadEvent.Done -> {
                        val ok = apkInstaller.launchInstall(event.file)
                        _uiState.value = _uiState.value.copy(
                            downloading = false, downloadedFile = event.file,
                            installLaunched = ok, installFailed = !ok,
                        )
                    }
                    is DownloadEvent.Failed ->
                        _uiState.value = _uiState.value.copy(
                            downloading = false, message = event.reason,
                        )
                }
            }
        }
    }

    fun retryInstall() {
        val file = _uiState.value.downloadedFile ?: return
        val ok = apkInstaller.launchInstall(file)
        _uiState.value = _uiState.value.copy(installLaunched = ok, installFailed = !ok)
    }
}
