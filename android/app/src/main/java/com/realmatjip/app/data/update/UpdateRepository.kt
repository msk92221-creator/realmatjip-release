package com.realmatjip.app.data.update

import java.io.File

/**
 * GitHub Releases 업데이트 시스템 (스펙 §10 / DESIGN D2).
 *
 * - 토큰 없이 releases/latest 조회 — 24h 스로틀 + ETag 조건부 요청
 * - 자산: realmatjip-universal.apk + .apk.sha256 + update-config.json
 * - pre-release/draft 릴리즈는 무시 (latest 엔드포인트가 원래 제외하지만 이중 방어)
 * - SHA-256 불일치 시 설치 금지·파일 삭제, 실패해도 앱 사용 가능, 자동 설치 금지
 */
interface UpdateRepository {
    suspend fun checkForUpdate(force: Boolean = false): UpdateState
    fun downloadApk(update: UpdateState.Available): kotlinx.coroutines.flow.Flow<DownloadEvent>
}

sealed interface UpdateState {
    data object UpToDate : UpdateState
    data object Throttled : UpdateState

    /** 업데이트 가능 — mandatory면 최소 버전 미만으로 강제 업데이트 대상. */
    data class Available(
        val version: String,
        val notes: String,
        val mandatory: Boolean,
        val apkUrl: String,
        val apkSizeBytes: Long,
        val expectedSha256: String?,
    ) : UpdateState

    data class Unavailable(val reason: String) : UpdateState
}

/** APK 다운로드 이벤트 — 진행률 → 완료(검증 통과 파일) 또는 실패(파일 정리됨). */
sealed interface DownloadEvent {
    data class Progress(val bytes: Long, val totalBytes: Long) : DownloadEvent
    data class Done(val file: File) : DownloadEvent
    data class Failed(val reason: String) : DownloadEvent
}

/** update-config.json (릴리즈 자산) — 머신리더블 설정 (스펙: 릴리즈 노트와 분리). */
@kotlinx.serialization.Serializable
data class UpdateConfig(
    val minimumVersion: String? = null,
    val mandatory: Boolean = false,
)
