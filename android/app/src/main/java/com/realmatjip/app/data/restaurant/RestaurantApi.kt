package com.realmatjip.app.data.restaurant

import com.realmatjip.app.data.restaurant.dto.LabelRequestDto
import com.realmatjip.app.data.restaurant.dto.LabelResponseDto
import com.realmatjip.app.data.restaurant.dto.MetaDto
import com.realmatjip.app.data.restaurant.dto.RestaurantDetailResponseDto
import com.realmatjip.app.data.restaurant.dto.RestaurantListResponseDto
import com.realmatjip.app.data.restaurant.dto.ReviewsResponseDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface RestaurantApi {

    @GET("/api/restaurants")
    suspend fun list(
        @Query("q") query: String? = null,
        @Query("category") category: String? = null,
        @Query("local_only") localOnly: Boolean? = null,
        @Query("min_overall") minOverall: Double? = null,
        @Query("sort") sort: String? = null,
        @Query("bbox") bbox: String? = null,
        @Query("limit") limit: Int? = null,
    ): RestaurantListResponseDto

    @GET("/api/restaurants/{id}")
    suspend fun detail(@Path("id") id: String): RestaurantDetailResponseDto

    @GET("/api/restaurants/{id}/reviews")
    suspend fun reviews(
        @Path("id") id: String,
        @Query("ad_filter") adFilter: String,
        @Query("limit") limit: Int? = null,
    ): ReviewsResponseDto

    @POST("/api/reviews/{id}/label")
    suspend fun setLabel(
        @Path("id") reviewId: String,
        @Body body: LabelRequestDto,
    ): LabelResponseDto

    @GET("/api/meta")
    suspend fun meta(): MetaDto
}
