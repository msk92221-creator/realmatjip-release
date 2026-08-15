package com.realmatjip.app.data.update

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.io.File

/** Phase 4 업데이트 시스템 단위 테스트 — MockWebServer + Robolectric. */
@RunWith(RobolectricTestRunner::class)
class GitHubUpdateRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var context: Context
    private val store = FakeStore()
    private var nowMs = 1_000_000L

    private lateinit var repo: GitHubUpdateRepository

    @Before
    fun setup() {
        server = MockWebServer()
        server.start()
        context = ApplicationProvider.getApplicationContext()
        repo = GitHubUpdateRepository(
            context = context,
            okHttpClient = OkHttpClient(),
            store = store,
            json = Json { ignoreUnknownKeys = true },
            currentVersion = "0.2.0",
            releaseRepoSlug = "test/repo",
        )
        repo.apiBaseUrl = server.url("/").toString().trimEnd('/')
        repo.clockMs = { nowMs }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun url(path: String): String = server.url(path).toString()

    private fun releaseJson(
        tag: String = "v0.3.0",
        draft: Boolean = false,
        prerelease: Boolean = false,
        withConfig: Boolean = true,
        withSha: Boolean = true,
    ): String {
        val assets = buildString {
            append("""{"name":"realmatjip-universal.apk","browser_download_url":"${url("/apk.bin")}","size":1234}""")
            if (withSha) {
                append(",")
                append("""{"name":"realmatjip-universal.apk.sha256","browser_download_url":"${url("/repo.apk.sha256")}","size":64}""")
            }
            if (withConfig) {
                append(",")
                append("""{"name":"update-config.json","browser_download_url":"${url("/update-config.json")}","size":50}""")
            }
        }
        return """
        {"tag_name":"$tag","name":"릴리즈 $tag","body":"변경 내용",
         "draft":$draft,"prerelease":$prerelease,"assets":[$assets]}
        """.trimIndent()
    }

    private fun enqueueReleaseAssets(config: String = """{"minimumVersion":null,"mandatory":false}""",
                                     sha: String = "0".repeat(64)) {
        server.enqueue(MockResponse().setBody(config))        // update-config.json
        server.enqueue(MockResponse().setBody(sha))           // .apk.sha256
    }

    @Test
    fun `새 버전 있음 - 자산과 메타 수집`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson()).setHeader("ETag", "\"e1\""))
        enqueueReleaseAssets()

        val state = repo.checkForUpdate(force = true)

        assertTrue(state is UpdateState.Available)
        state as UpdateState.Available
        assertEquals("0.3.0", state.version)
        assertFalse(state.mandatory)
        assertEquals(1234L, state.apkSizeBytes)
        assertEquals("0".repeat(64), state.expectedSha256)
        assertEquals("\"e1\"", store.etagSaved)
        assertEquals(nowMs, store.checkedAtSaved)
    }

    @Test
    fun `오래된 버전 - UpToDate`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson(tag = "v0.1.0")))
        // parseRelease에서 버전 비교 후 자산 fetch 없음 — 추가 응답 불필요

        val state = repo.checkForUpdate(force = true)
        assertTrue(state is UpdateState.UpToDate)
    }

    @Test
    fun `같은 버전이어도 pre-release 태그면 UpToDate`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson(tag = "v0.2.0")))
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.UpToDate)
    }

    @Test
    fun `draft와 prerelease 플래그는 Unavailable`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson(draft = true)))
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.Unavailable)
        server.enqueue(MockResponse().setBody(releaseJson(prerelease = true)))
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.Unavailable)
    }

    @Test
    fun `minimumVersion 미만이면 mandatory`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson()))
        enqueueReleaseAssets(config = """{"minimumVersion":"0.3.0","mandatory":false}""")

        val state = repo.checkForUpdate(force = true) as UpdateState.Available
        assertTrue(state.mandatory)
    }

    @Test
    fun `config mandatory 플래그 반영`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson()))
        enqueueReleaseAssets(config = """{"mandatory":true}""")

        val state = repo.checkForUpdate(force = true) as UpdateState.Available
        assertTrue(state.mandatory)
    }

    @Test
    fun `config 파싱 실패시 기본값으로 동작`() = runBlocking {
        server.enqueue(MockResponse().setBody(releaseJson()))
        server.enqueue(MockResponse().setBody("{not json"))  // config 깨짐
        server.enqueue(MockResponse().setBody("0".repeat(64)))

        val state = repo.checkForUpdate(force = true) as UpdateState.Available
        assertFalse(state.mandatory)
    }

    @Test
    fun `APK 자산이 없으면 Unavailable`() = runBlocking {
        server.enqueue(MockResponse().setBody(
            """{"tag_name":"v0.3.0","assets":[{"name":"notes.txt"}]}"""))
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.Unavailable)
    }

    @Test
    fun `304 Not Modified는 UpToDate`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(304))
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.UpToDate)
    }

    @Test
    fun `24h 스로틀 - 마지막 확인 1시간 전이면 Throttled`() = runBlocking {
        store.checkedAtToReturn = nowMs - 3_600_000L
        val state = repo.checkForUpdate(force = false)
        assertTrue(state is UpdateState.Throttled)
        assertEquals(0, server.requestCount) // 네트워크 호출 없음
    }

    @Test
    fun `스로틀지난 확인은 네트워크 호출`() = runBlocking {
        store.checkedAtToReturn = nowMs - 25 * 3_600_000L
        server.enqueue(MockResponse().setBody(releaseJson()))
        enqueueReleaseAssets()
        assertTrue(repo.checkForUpdate(force = false) is UpdateState.Available)
    }

    @Test
    fun `force는 스로틀 무시`() = runBlocking {
        store.checkedAtToReturn = nowMs // 방금 확인함
        server.enqueue(MockResponse().setBody(releaseJson()))
        enqueueReleaseAssets()
        assertTrue(repo.checkForUpdate(force = true) is UpdateState.Available)
    }

    @Test
    fun `저장된 ETag를 If-None-Match로 전송`() = runBlocking {
        store.etagToReturn = "\"etag-42\""
        server.enqueue(MockResponse().setBody(releaseJson()))
        enqueueReleaseAssets()
        repo.checkForUpdate(force = true)

        val request = server.takeRequest()
        assertEquals("\"etag-42\"", request.getHeader("If-None-Match"))
        assertEquals("application/vnd.github+json", request.getHeader("Accept"))
        assertTrue(request.path!!.contains("/repos/test/repo/releases/latest"))
    }

    @Test
    fun `다운로드 성공 - SHA 일치시 Done`() = runBlocking {
        val apkBytes = ByteArray(4096) { (it % 251).toByte() }
        server.enqueue(MockResponse().setBody(okio.Buffer().write(apkBytes)))

        val temp = File.createTempFile("expected", ".apk").apply {
            writeBytes(apkBytes)
            deleteOnExit()
        }
        val expected = repo.sha256Of(temp)

        val update = UpdateState.Available(
            version = "0.3.0", notes = "", mandatory = false,
            apkUrl = url("/apk.bin"), apkSizeBytes = apkBytes.size.toLong(),
            expectedSha256 = expected,
        )
        val events = repo.downloadApk(update).toList()

        assertTrue(events.last() is DownloadEvent.Done)
        val file = (events.last() as DownloadEvent.Done).file
        assertTrue(file.exists())
        assertEquals(apkBytes.size.toLong(), file.length())
        file.delete()
        Unit
    }

    @Test
    fun `SHA 불일치 - 파일 삭제 후 Failed`() = runBlocking {
        server.enqueue(MockResponse().setBody(okio.Buffer().write(ByteArray(1024))))
        val update = UpdateState.Available(
            version = "0.3.0", notes = "", mandatory = false,
            apkUrl = url("/apk.bin"), apkSizeBytes = 1024,
            expectedSha256 = "f".repeat(64), // 절대 불일치
        )
        val events = repo.downloadApk(update).toList()

        assertTrue(events.last() is DownloadEvent.Failed)
        val updatesDir = File(context.cacheDir, "updates")
        val leftovers = updatesDir.listFiles()?.filter { it.name.contains("0.3.0") } ?: emptyList()
        assertTrue(leftovers.isEmpty()) // 검증 실패 파일은 삭제되어야 한다 (스펙 §10)
    }

    /** 메모리 UpdateCheckStore — 스로틀/ETag 상태 시뮬레이션. */
    private class FakeStore : UpdateCheckStore {
        var etagToReturn = ""
        var checkedAtToReturn = 0L
        var etagSaved = ""
        var checkedAtSaved = 0L

        override suspend fun lastCheckEpochMs(): Long = checkedAtToReturn
        override suspend fun etag(): String = etagToReturn
        override suspend fun save(etag: String, checkedAtMs: Long) {
            etagSaved = etag
            checkedAtSaved = checkedAtMs
        }
    }
}
