package com.realmatjip.app.data.admin

import com.realmatjip.app.data.admin.dto.AnalyzeEstimateDto
import com.realmatjip.app.data.admin.dto.ImportCommitDto
import com.realmatjip.app.data.admin.dto.ImportPreviewDto
import com.realmatjip.app.data.restaurant.dto.HealthDto
import com.realmatjip.app.data.restaurant.dto.JobDto
import com.realmatjip.app.data.restaurant.dto.LabelRequestDto
import com.realmatjip.app.data.restaurant.dto.RecalculateResponseDto
import com.realmatjip.app.data.restaurant.dto.SeedResponseDto
import com.realmatjip.app.data.restaurant.dto.StatsDto
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface AdminApi {

    @POST("/api/admin/recalculate")
    suspend fun recalculate(): RecalculateResponseDto

    @GET("/api/admin/jobs/{id}")
    suspend fun job(@Path("id") jobId: Int): JobDto

    @GET("/api/admin/stats")
    suspend fun stats(): StatsDto

    @POST("/api/admin/seed")
    suspend fun seed(@Query("reset") reset: Boolean = false): SeedResponseDto

    @GET("/api/backup/export")
    suspend fun export(): ResponseBody

    @GET("/health")
    suspend fun health(): HealthDto

    @POST("/api/admin/import/preview")
    suspend fun importPreview(@Body body: ImportRequestBody): ImportPreviewDto

    @POST("/api/admin/import/commit")
    suspend fun importCommit(@Body body: ImportRequestBody): ImportCommitDto

    @POST("/api/admin/analyze/preview")
    suspend fun analyzePreview(): AnalyzeEstimateDto

    @POST("/api/admin/analyze-pending")
    suspend fun analyzePending(): RecalculateResponseDto
}

@kotlinx.serialization.Serializable
data class ImportRequestBody(
    val format: String,
    val content: String,
)
