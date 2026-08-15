package com.realmatjip.app.feature.developer

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.userMessage
import com.realmatjip.app.domain.model.AnalyzeEstimate
import com.realmatjip.app.domain.model.BackendMeta
import com.realmatjip.app.domain.model.BackendStats
import com.realmatjip.app.domain.model.GoogleImportCommit
import com.realmatjip.app.domain.model.GoogleImportPreview
import com.realmatjip.app.domain.model.GooglePlace
import com.realmatjip.app.domain.model.ImportCommit
import com.realmatjip.app.domain.model.ImportPreview
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.domain.repository.AdminRepository
import com.realmatjip.app.domain.repository.ProviderRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject

/** Developer 화면 (스펙 §10) — Import preview/commit, LLM 분석 잡, 재계산, 백업. */
    @HiltViewModel
    class DeveloperViewModel @Inject constructor(
        @ApplicationContext private val context: Context,
        private val adminRepository: AdminRepository,
        private val restaurantRepository: RestaurantRepository,
        private val providerRepository: ProviderRepository,
        private val updateRepository: com.realmatjip.app.data.update.UpdateRepository,
    ) : ViewModel() {

    /** Import 화면 상태 (스펙 §10) */
    data class ImportUiState(
        val format: String = "json",           // json | csv
        val content: String = "",
        val running: Boolean = false,
        val preview: ImportPreview? = null,
        val commit: ImportCommit? = null,
        val error: String? = null,
    ) {
        val canPreview: Boolean get() = content.isNotBlank() && !running
        val canCommit: Boolean get() = preview != null && preview.estimatedNewReviews > 0 && !running
    }

    /** LLM 분석 상태 */
    data class AnalyzeUiState(
        val estimate: AnalyzeEstimate? = null,
        val running: Boolean = false,
        val job: JobInfo? = null,
        val error: String? = null,
    )

    /** Google Places 검색 상태 (스펙 §22) */
    data class GoogleUiState(
        val query: String = "",
        val searching: Boolean = false,
        val results: List<GooglePlace> = emptyList(),
        val selectedPlaceId: String? = null,
        val preview: GoogleImportPreview? = null,
        val committing: Boolean = false,
        val commitResult: GoogleImportCommit? = null,
        val error: String? = null,
    )

    data class UiState(
        val loading: Boolean = true,
        val backendStatus: String? = null,
        val backendError: String? = null,
        val meta: BackendMeta? = null,
        val stats: BackendStats? = null,
        val job: JobInfo? = null,
        val jobError: String? = null,
        val notice: String? = null,
        val importState: ImportUiState = ImportUiState(),
        val analyzeState: AnalyzeUiState = AnalyzeUiState(),
        val googleState: GoogleUiState = GoogleUiState(),
        val updateCheck: String? = null,
        val updateChecking: Boolean = false,
    )

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    var pollIntervalMs: Long = 1500L

    /** 테스트에서 가상 시간으로 교체 가능 */
    var ioDispatcher: kotlinx.coroutines.CoroutineDispatcher = Dispatchers.IO

    init {
        refresh()
    }

    /** Phase 4: 스로틀 무시하고 즉시 releases/latest 확인 (스펙 §10). */
    fun forceUpdateCheck() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(updateChecking = true, updateCheck = null)
            val message = when (val state = updateRepository.checkForUpdate(force = true)) {
                is com.realmatjip.app.data.update.UpdateState.Available ->
                    "업데이트 있음 v${state.version}" +
                    (if (state.mandatory) " (필수)" else "") +
                    " — 설정 화면에서 다운로드"
                is com.realmatjip.app.data.update.UpdateState.UpToDate -> "최신 버전"
                is com.realmatjip.app.data.update.UpdateState.Throttled -> "스로틀 중 (24h)"
                is com.realmatjip.app.data.update.UpdateState.Unavailable -> "실패: ${state.reason}"
            }
            _uiState.value = _uiState.value.copy(updateChecking = false, updateCheck = message)
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(loading = true, backendError = null, backendStatus = null)
            when (val health = restaurantRepository.testConnection()) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(backendStatus = health.data)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(backendError = health.error.userMessage())
            }
            when (val meta = restaurantRepository.meta()) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(meta = meta.data)
                is ApiResult.Failure -> Unit
            }
            when (val stats = adminRepository.stats()) {
                is ApiResult.Success -> _uiState.value = _uiState.value.copy(stats = stats.data, loading = false)
                is ApiResult.Failure -> _uiState.value = _uiState.value.copy(loading = false)
            }
        }
    }

    // ── Import (스펙 §10) ─────────────────────────────────────

    fun onImportFormatChange(format: String) {
        _uiState.value = _uiState.value.copy(
            importState = _uiState.value.importState.copy(format = format, preview = null, commit = null),
        )
    }

    fun onImportContentChange(content: String) {
        _uiState.value = _uiState.value.copy(
            importState = _uiState.value.importState.copy(content = content, preview = null, commit = null),
        )
    }

    /** 파일 선택 결과 — 내용을 입력란에 반영 */
    fun onImportFile(content: String?) {
        if (!content.isNullOrBlank()) onImportContentChange(content)
    }

    fun previewImport() {
        val current = _uiState.value.importState
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                importState = current.copy(running = true, error = null),
            )
            val result = adminRepository.importPreview(current.format, current.content)
            _uiState.value = _uiState.value.copy(
                importState = _uiState.value.importState.copy(
                    running = false,
                    preview = (result as? ApiResult.Success)?.data,
                    error = (result as? ApiResult.Failure)?.error?.userMessage(),
                ),
            )
        }
    }

    fun commitImport() {
        val current = _uiState.value.importState
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                importState = current.copy(running = true, error = null),
            )
            val result = adminRepository.importCommit(current.format, current.content)
            _uiState.value = _uiState.value.copy(
                importState = _uiState.value.importState.copy(
                    running = false,
                    commit = (result as? ApiResult.Success)?.data,
                    error = (result as? ApiResult.Failure)?.error?.userMessage(),
                ),
            )
            refresh()
        }
    }

    // ── LLM 분석 (스펙 §10) ──────────────────────────────────

    fun loadAnalyzeEstimate() {
        viewModelScope.launch {
            when (val result = adminRepository.analyzeEstimate()) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(
                        analyzeState = _uiState.value.analyzeState.copy(estimate = result.data, error = null),
                    )
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        analyzeState = _uiState.value.analyzeState.copy(error = result.error.userMessage()),
                    )
            }
        }
    }

    fun analyzePending() {
        if (_uiState.value.analyzeState.running) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                analyzeState = AnalyzeUiState(running = true),
            )
            when (val start = adminRepository.analyzePending()) {
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        analyzeState = AnalyzeUiState(error = start.error.userMessage()),
                    )
                is ApiResult.Success -> {
                    var job = JobInfo(start.data, "analyze-pending", "queued", null)
                    _uiState.value = _uiState.value.copy(
                        analyzeState = _uiState.value.analyzeState.copy(job = job),
                    )
                    while (viewModelScope.coroutineContext.isActive) {
                        when (val polled = adminRepository.job(start.data)) {
                            is ApiResult.Success -> {
                                job = polled.data
                                _uiState.value = _uiState.value.copy(
                                    analyzeState = _uiState.value.analyzeState.copy(job = job),
                                )
                                if (job.isFinished) break
                            }
                            is ApiResult.Failure -> {
                                _uiState.value = _uiState.value.copy(
                                    analyzeState = _uiState.value.analyzeState.copy(
                                        running = false, error = polled.error.userMessage(),
                                    ),
                                )
                                return@launch
                            }
                        }
                        delay(pollIntervalMs)
                    }
                    _uiState.value = _uiState.value.copy(
                        analyzeState = _uiState.value.analyzeState.copy(
                            running = false,
                            error = if (job.status == "failed") job.error else null,
                        ),
                    )
                    refresh()
                }
            }
        }
    }

    // ── 재계산 / 시드 / 백업 (Phase 2에서 이어짐) ─────────────

    fun recalculate() {
        if (_uiState.value.job?.isFinished == false) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(job = null, jobError = null, notice = null)
            when (val start = adminRepository.recalculate()) {
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(jobError = start.error.userMessage())
                is ApiResult.Success -> {
                    var job = JobInfo(start.data, "recalculate", "queued", null)
                    _uiState.value = _uiState.value.copy(job = job)
                    while (viewModelScope.coroutineContext.isActive) {
                        when (val polled = adminRepository.job(start.data)) {
                            is ApiResult.Success -> {
                                job = polled.data
                                _uiState.value = _uiState.value.copy(job = job)
                                if (job.isFinished) break
                            }
                            is ApiResult.Failure -> {
                                _uiState.value = _uiState.value.copy(jobError = polled.error.userMessage())
                                return@launch
                            }
                        }
                        delay(pollIntervalMs)
                    }
                    _uiState.value = _uiState.value.copy(
                        notice = if (job.status == "done") "재계산 완료" else "재계산 실패: ${job.error ?: ""}",
                    )
                    refresh()
                }
            }
        }
    }

    fun seed(reset: Boolean) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(notice = "시드 처리 중…")
            when (val result = adminRepository.seed(reset)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(notice = "시드 완료 — ${result.data}")
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(jobError = result.error.userMessage())
            }
            refresh()
        }
    }

    /** DB Backup — export JSON을 앱 전용 디렉터리에 저장 */
    fun backup() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(notice = "백업 내려받는 중…")
            when (val result = adminRepository.backupExport()) {
                is ApiResult.Success -> {
                    val path = withContext(ioDispatcher) {
                        val dir = File(context.filesDir, "backups").apply { mkdirs() }
                        val file = File(dir, "realmatjip-backup-${System.currentTimeMillis()}.json")
                        file.writeText(result.data, Charsets.UTF_8)
                        file.absolutePath
                    }
                    _uiState.value = _uiState.value.copy(notice = "백업 저장: $path")
                }
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(jobError = result.error.userMessage())
            }
        }
    }

    fun testConnection() {
        viewModelScope.launch {
            when (val health = restaurantRepository.testConnection()) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(backendStatus = health.data, backendError = null)
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(backendError = health.error.userMessage())
            }
        }
    }

    // ── Google Places (Phase 3B, 스펙 §22) ────────────────────

    fun onGoogleQueryChange(query: String) {
        _uiState.value = _uiState.value.copy(
            googleState = _uiState.value.googleState.copy(query = query),
        )
    }

    fun searchGooglePlaces() {
        val query = _uiState.value.googleState.query
        if (query.isBlank()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                googleState = _uiState.value.googleState.copy(
                    searching = true, results = emptyList(), error = null,
                    preview = null, commitResult = null, selectedPlaceId = null,
                ),
            )
            when (val result = providerRepository.search(query)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(
                            searching = false, results = result.data,
                        ),
                    )
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(
                            searching = false, error = result.error.userMessage(),
                        ),
                    )
            }
        }
    }

    fun googlePreview(placeId: String) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                googleState = _uiState.value.googleState.copy(
                    selectedPlaceId = placeId, preview = null, error = null, commitResult = null,
                ),
            )
            when (val result = providerRepository.importPreview(placeId)) {
                is ApiResult.Success ->
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(preview = result.data),
                    )
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(error = result.error.userMessage()),
                    )
            }
        }
    }

    fun googleCommit(forceNew: Boolean = false) {
        val placeId = _uiState.value.googleState.selectedPlaceId ?: return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(
                googleState = _uiState.value.googleState.copy(committing = true, error = null),
            )
            when (val result = providerRepository.importCommit(placeId, forceNew)) {
                is ApiResult.Success -> {
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(
                            committing = false, commitResult = result.data,
                        ),
                    )
                    refresh()
                }
                is ApiResult.Failure ->
                    _uiState.value = _uiState.value.copy(
                        googleState = _uiState.value.googleState.copy(
                            committing = false, error = result.error.userMessage(),
                        ),
                    )
            }
        }
    }
}
