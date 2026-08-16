package com.realmatjip.app.data.update

import android.content.Context
import com.realmatjip.app.core.update.SemVer
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton

/**
 * GitHub Releases 기반 업데이트 구현 (스펙 §10).
 *
 * 확인 흐름: 24h 스로틀 → ETag 조건부 GET /releases/latest → draft/pre-release 제외
 * → SemVer 비교 → update-config.json의 minimumVersion/mandatory 반영.
 * 다운로드 흐름: 캐시 디렉터리에 스트리밍 → SHA-256 검증 → 불일치 시 파일 삭제.
 */
@Singleton
class GitHubUpdateRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    @javax.inject.Named("noAuth") private val okHttpClient: OkHttpClient,
    private val store: UpdateCheckStore,
    private val json: Json,
    @javax.inject.Named("currentVersion") private val currentVersion: String,
    @javax.inject.Named("releaseRepoSlug") private val releaseRepoSlug: String,
) : UpdateRepository {

    /** 테스트 주입용 — 운영은 기본값 사용. */
    var apiBaseUrl: String = DEFAULT_API_BASE
    var clockMs: () -> Long = System::currentTimeMillis

    private val throttleMs = THROTTLE_HOURS * 3_600_000L

    override suspend fun checkForUpdate(force: Boolean): UpdateState = withContext(Dispatchers.IO) {
        val now = clockMs()
        if (!force && now - store.lastCheckEpochMs() < throttleMs) {
            return@withContext UpdateState.Throttled
        }
        val etag = store.etag()
        val request = Request.Builder()
            .url("${apiBaseUrl.trimEnd('/')}/repos/$releaseRepoSlug/releases/latest")
            .header("Accept", "application/vnd.github+json")
            .apply { if (etag.isNotEmpty()) header("If-None-Match", etag) }
            .build()

        okHttpClient.newCall(request).execute().use { response ->
            when {
                response.code == 304 -> {
                    store.save(etag, now)
                    return@withContext UpdateState.UpToDate // 변경 없음 — 마지막 확인 결과 유지
                }
                !response.isSuccessful ->
                    return@withContext UpdateState.Unavailable(
                        "GitHub 조회 실패 (HTTP ${response.code})")
            }
            val newEtag = response.header("ETag") ?: ""
            val body = response.body?.string()
                ?: return@withContext UpdateState.Unavailable("빈 응답")
            store.save(newEtag, now)
            parseRelease(body)
        }
    }

    /** 릴리즈 파싱 + 자산 수집 + 버전/강제 여부 판정 — 순수 로직 (단위 테스트 대상). */
    internal fun parseRelease(body: String): UpdateState {
        val release = runCatching { json.decodeFromString<GitHubRelease>(body) }
            .getOrElse { return UpdateState.Unavailable("응답 파싱 실패: ${it.message}") }
        if (release.draft || release.prerelease) {
            return UpdateState.Unavailable("릴리즈가 draft/pre-release임")
        }
        val tag = release.tagName?.trim().orEmpty()
        val releaseVersion = SemVer.parseOrNull(tag)
            ?: return UpdateState.Unavailable("태그를 버전으로 해석 불가: '$tag'")
        val current = SemVer.parseOrNull(currentVersion)
            ?: return UpdateState.Unavailable("현재 버전 해석 불가: '$currentVersion'")
        if (releaseVersion <= current) return UpdateState.UpToDate

        val apkAsset = release.assets.firstOrNull { it.name.endsWith(".apk") }
            ?: return UpdateState.Unavailable("APK 자산이 없음")
        val apkUrl = apkAsset.browserDownloadUrl
            ?: return UpdateState.Unavailable("APK 다운로드 URL이 없음")
        val shaAsset = release.assets.firstOrNull { it.name.endsWith(".sha256") }
        val configAsset = release.assets.firstOrNull { it.name == "update-config.json" }

        val config = configAsset?.browserDownloadUrl
            ?.let { runCatching { fetchText(it) }.getOrNull() }
            ?.let { runCatching { json.decodeFromString<UpdateConfig>(it) }.getOrNull() }
            ?: UpdateConfig()
        val minimum = SemVer.parseOrNull(config.minimumVersion)
        val mandatory = config.mandatory || (minimum != null && current < minimum)

        return UpdateState.Available(
            version = releaseVersion.toString(),
            notes = (release.name ?: tag) + (release.body?.let { "\n\n$it" } ?: ""),
            mandatory = mandatory,
            apkUrl = apkUrl,
            apkSizeBytes = apkAsset.size,
            expectedSha256 = shaAsset?.browserDownloadUrl
                ?.let { runCatching { fetchText(it) }.getOrNull() }
                ?.trim()?.split(Regex("\\s+"))?.firstOrNull { it.length == 64 },
        )
    }

    private fun fetchText(url: String): String =
        okHttpClient.newCall(Request.Builder().url(url).build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("HTTP ${resp.code}")
            resp.body?.string() ?: ""
        }

    override fun downloadApk(update: UpdateState.Available): Flow<DownloadEvent> = flow {
        val dir = File(context.cacheDir, "updates").apply { mkdirs() }
        val target = File(dir, "realmatjip-${update.version}.apk")
        try {
            val request = Request.Builder().url(update.apkUrl).build()
            okHttpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    emit(DownloadEvent.Failed("다운로드 실패 (HTTP ${response.code})"))
                    return@flow
                }
                val body = response.body
                    ?: throw IllegalStateException("빈 응답 본문")
                val total = body.contentLength().takeIf { it > 0 } ?: update.apkSizeBytes
                var written = 0L
                target.outputStream().use { out ->
                    val input = body.byteStream()
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    while (true) {
                        val read = input.read(buffer)
                        if (read == -1) break
                        out.write(buffer, 0, read)
                        written += read
                        emit(DownloadEvent.Progress(written, total))
                    }
                }
            }
            // SHA-256 검증 — 불일치 시 설치 금지·파일 삭제 (스펙 §10)
            val expected = update.expectedSha256
            if (expected != null) {
                val actual = sha256Of(target)
                if (!actual.equals(expected, ignoreCase = true)) {
                    target.delete()
                    emit(DownloadEvent.Failed(
                        "SHA-256 불일치 — 기대 ${expected.take(12)}… 실제 ${actual.take(12)}… (파일 삭제됨)"))
                    return@flow
                }
            }
            emit(DownloadEvent.Done(target))
        } catch (e: Exception) {
            target.delete()
            emit(DownloadEvent.Failed("다운로드 오류: ${e.message}"))
        }
    }.flowOn(Dispatchers.IO)

    internal fun sha256Of(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read == -1) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    companion object {
        const val THROTTLE_HOURS = 24
        const val DEFAULT_API_BASE = "https://api.github.com"

        /** D2: 앱 코드와 릴리즈를 분리한 public 릴리즈 저장소. */
        const val DEFAULT_RELEASE_REPO = "msk92221-creator/realmatjip-release"
    }
}
