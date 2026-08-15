package com.realmatjip.app.feature

import com.realmatjip.app.FakeAdminRepository
import com.realmatjip.app.FakeUpdateRepository
import com.realmatjip.app.FakeProviderRepository
import com.realmatjip.app.FakeRestaurantRepository
import com.realmatjip.app.MainDispatcherRule
import com.realmatjip.app.feature.developer.DeveloperViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class DeveloperViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private fun viewModel(
        adminRepo: FakeAdminRepository = FakeAdminRepository(),
    ): DeveloperViewModel {
        val appContext = org.robolectric.RuntimeEnvironment.getApplication()
        return DeveloperViewModel(appContext, adminRepo, FakeRestaurantRepository(), FakeProviderRepository(), FakeUpdateRepository())
    }

    @Test
    fun `초기 로드 - 상태 메타 통계`() {
        val viewModel = viewModel()
        mainDispatcherRule.advanceUntilIdle()

        val state = viewModel.uiState.value
        assertNotNull(state.backendStatus)
        assertEquals("v0.1-phase0", state.meta?.algorithmVersion)
        assertEquals(175, state.stats?.reviews)
        assertEquals(0, state.stats?.unanalyzed)
    }

    @Test
    fun `재계산 잡 진행률 폴링 후 완료`() {
        val adminRepo = FakeAdminRepository()
        val viewModel = viewModel(adminRepo)
        viewModel.pollIntervalMs = 10
        mainDispatcherRule.advanceUntilIdle()

        viewModel.recalculate()
        mainDispatcherRule.advanceUntilIdle()

        // queued → running → done 순서로 폴링되었는지
        assertEquals(1, adminRepo.recalculateCalls)
        assertTrue(adminRepo.jobCallCount >= 3)
        assertEquals("재계산 완료", viewModel.uiState.value.notice)
        val job = viewModel.uiState.value.job
        assertNotNull(job)
        assertEquals("done", job!!.status)
        assertEquals(5, job.done)
        assertEquals(5, job.total)
    }

    @Test
    fun `백업 export 호출`() {
        val adminRepo = FakeAdminRepository()
        val viewModel = viewModel(adminRepo)
        viewModel.ioDispatcher = kotlinx.coroutines.Dispatchers.Unconfined
        mainDispatcherRule.advanceUntilIdle()

        viewModel.backup()
        mainDispatcherRule.advanceUntilIdle()

        assertTrue(viewModel.uiState.value.notice!!.contains("백업 저장:"))
    }
}
