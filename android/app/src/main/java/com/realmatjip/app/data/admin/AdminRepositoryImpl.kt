package com.realmatjip.app.data.admin

import com.realmatjip.app.core.network.ApiClient
import com.realmatjip.app.core.network.ApiResult
import com.realmatjip.app.core.network.apiCall
import com.realmatjip.app.domain.model.AnalyzeEstimate
import com.realmatjip.app.domain.model.BackendStats
import com.realmatjip.app.domain.model.ImportCommit
import com.realmatjip.app.domain.model.ImportPreview
import com.realmatjip.app.domain.model.ImportRowError
import com.realmatjip.app.domain.model.JobInfo
import com.realmatjip.app.domain.repository.AdminRepository
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AdminRepositoryImpl @Inject constructor(
    private val apiClient: ApiClient,
) : AdminRepository {

    private fun api(): AdminApi = apiClient.service(AdminApi::class)

    override suspend fun recalculate(): ApiResult<Int> = apiCall {
        api().recalculate().jobId
    }

    override suspend fun analyzePending(): ApiResult<Int> = apiCall {
        api().analyzePending().jobId
    }

    override suspend fun job(jobId: Int): ApiResult<JobInfo> = apiCall {
        val dto = api().job(jobId)
        val progress = dto.progress
        JobInfo(
            id = dto.id,
            kind = dto.kind,
            status = dto.status,
            error = dto.error,
            done = progress?.intOrNull("done"),
            total = progress?.intOrNull("total"),
            completed = progress?.intOrNull("completed"),
            cached = progress?.intOrNull("cached"),
            failed = progress?.intOrNull("failed"),
            tokensInput = progress?.longOrNull("tokens_input"),
            tokensOutput = progress?.longOrNull("tokens_output"),
            estimatedCost = progress?.doubleOrNull("estimated_cost"),
            analyzer = progress?.stringOrNull("analyzer"),
            model = progress?.stringOrNull("model"),
            promptVersion = progress?.stringOrNull("prompt_version"),
        )
    }

    override suspend fun stats(): ApiResult<BackendStats> = apiCall {
        val dto = api().stats()
        BackendStats(
            restaurants = dto.restaurants,
            reviews = dto.reviews,
            analyzed = dto.analyzed,
            unanalyzed = dto.unanalyzed,
            duplicateFlagged = dto.duplicateFlagged,
            manualLabels = dto.manualLabels,
            reviewsBySource = dto.reviewsBySource,
            latestScoreCalculatedAt = dto.latestScore?.calculatedAt,
            algorithmVersion = dto.latestScore?.algorithmVersion,
        )
    }

    override suspend fun seed(reset: Boolean): ApiResult<String> = apiCall {
        val response = api().seed(reset)
        "식당 ${response.seeded.restaurants}개 / 리뷰 ${response.seeded.reviews}개" +
            if (reset) " (초기화 후)" else ""
    }

    override suspend fun backupExport(): ApiResult<String> = apiCall {
        api().export().string()
    }

    override suspend fun importPreview(format: String, content: String): ApiResult<ImportPreview> =
        apiCall {
            val dto = api().importPreview(ImportRequestBody(format, content))
            ImportPreview(
                total = dto.total, valid = dto.valid, invalid = dto.invalid,
                exactDuplicates = dto.exactDuplicates,
                estimatedNewReviews = dto.estimatedNewReviews,
                newRestaurants = dto.newRestaurants, matchedRestaurants = dto.matchedRestaurants,
                errors = dto.errors.map { ImportRowError(it.row, it.field, it.reason) },
            )
        }

    override suspend fun importCommit(format: String, content: String): ApiResult<ImportCommit> =
        apiCall {
            val dto = api().importCommit(ImportRequestBody(format, content))
            ImportCommit(
                insertedRestaurants = dto.insertedRestaurants,
                insertedReviews = dto.insertedReviews,
                skippedDuplicates = dto.skippedDuplicates,
                invalid = dto.invalid,
                errors = dto.errors.map { ImportRowError(it.row, it.field, it.reason) },
            )
        }

    override suspend fun analyzeEstimate(): ApiResult<AnalyzeEstimate> = apiCall {
        val dto = api().analyzePreview()
        AnalyzeEstimate(
            analyzer = dto.analyzer, promptVersion = dto.promptVersion,
            pendingTotal = dto.pendingTotal, toAnalyze = dto.toAnalyze, cachedHits = dto.cachedHits,
            estimatedTokensInput = dto.estimatedTokensInput,
            estimatedTokensOutput = dto.estimatedTokensOutput,
            estimatedCost = dto.estimatedCost,
            withinLimits = dto.withinLimits, reviewsExceedCap = dto.reviewsExceedCap,
        )
    }
}

private fun JsonObject.intOrNull(key: String): Int? =
    (this[key] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()

private fun JsonObject.longOrNull(key: String): Long? =
    (this[key] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toLongOrNull()

private fun JsonObject.doubleOrNull(key: String): Double? =
    (this[key] as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull()

private fun JsonObject.stringOrNull(key: String): String? =
    (this[key] as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { it !is kotlinx.serialization.json.JsonNull }?.content
