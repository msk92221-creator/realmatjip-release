package com.realmatjip.app.feature

import com.realmatjip.app.FakeAdminRepository
import com.realmatjip.app.FakeUpdateRepository
import com.realmatjip.app.FakeProviderRepository
import com.realmatjip.app.FakeRestaurantRepository
import com.realmatjip.app.MainDispatcherRule
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.domain.model.ImportPreview
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.feature.developer.DeveloperViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class DeveloperImportAnalyzeTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private fun viewModel(adminRepo: FakeAdminRepository = FakeAdminRepository()): DeveloperViewModel {
        val appContext = org.robolectric.RuntimeEnvironment.getApplication()
        return DeveloperViewModel(appContext, adminRepo, FakeRestaurantRepository(), FakeProviderRepository(), FakeUpdateRepository())
    }

    @Test
    fun `import 미리보기 → 결과 표시 → 실행 가능`() {
        val adminRepo = FakeAdminRepository()
        val viewModel = viewModel(adminRepo)
        mainDispatcherRule.advanceUntilIdle()

        // 내용이 비어 있으면 미리보기 불가
        assertTrue(!viewModel.uiState.value.importState.canPreview)

        viewModel.onImportContentChange("""{"restaurants": []}""")
        assertTrue(viewModel.uiState.value.importState.canPreview)

        viewModel.previewImport()
        mainDispatcherRule.advanceUntilIdle()

        val preview = viewModel.uiState.value.importState.preview
        assertNotNull(preview)
        assertEquals(2, preview!!.estimatedNewReviews)
        assertEquals(1, preview.invalid)
        assertEquals("source", preview.errors.first().field)
        // 신규 리뷰가 있을 때만 Import 실행 가능
        assertTrue(viewModel.uiState.value.importState.canCommit)

        viewModel.commitImport()
        mainDispatcherRule.advanceUntilIdle()
        assertEquals(2, viewModel.uiState.value.importState.commit!!.insertedReviews)
    }

    @Test
    fun `분석 사용량 조회 후 잡 실행`() {
        val adminRepo = FakeAdminRepository()
        val viewModel = viewModel(adminRepo)
        viewModel.pollIntervalMs = 10
        mainDispatcherRule.advanceUntilIdle()

        viewModel.loadAnalyzeEstimate()
        mainDispatcherRule.advanceUntilIdle()
        assertEquals("mock-rules-v1", viewModel.uiState.value.analyzeState.estimate!!.analyzer)
        assertEquals(2, viewModel.uiState.value.analyzeState.estimate!!.toAnalyze)

        viewModel.analyzePending()
        mainDispatcherRule.advanceUntilIdle()

        assertEquals(1, adminRepo.analyzePendingCalls)
        val job = viewModel.uiState.value.analyzeState.job
        assertNotNull(job)
        assertEquals("done", job!!.status)
        assertTrue(!viewModel.uiState.value.analyzeState.running)
    }

    @Test
    fun `import 실패 시 오류 표시`() {
        val adminRepo = FakeAdminRepository().apply {
            importPreviewResult = ApiResult.Failure(
                com.realmatjip.app.core.network.ApiError.SERVER, "HTTP 500"
            )
        }
        val viewModel = viewModel(adminRepo)
        mainDispatcherRule.advanceUntilIdle()

        viewModel.onImportContentChange("x")
        viewModel.previewImport()
        mainDispatcherRule.advanceUntilIdle()

        assertNotNull(viewModel.uiState.value.importState.error)
        assertEquals(null, viewModel.uiState.value.importState.preview)
    }

    @Test
    fun `파일 내용 로드`() {
        val viewModel = viewModel()
        mainDispatcherRule.advanceUntilIdle()
        viewModel.onImportFile("restaurant_name,text")
        assertEquals("restaurant_name,text", viewModel.uiState.value.importState.content)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class JobInfoMappingTest {

    @Test
    fun `JobInfo 기본값과 완료 판정`() {
        val job = JobInfo(id = 1, kind = "analyze-pending", status = "running", error = null,
                          completed = 3, cached = 1, failed = 0)
        assertTrue(!job.isFinished)
        assertEquals(3, job.completed)
        assertEquals(null, job.tokensInput)
    }
}
