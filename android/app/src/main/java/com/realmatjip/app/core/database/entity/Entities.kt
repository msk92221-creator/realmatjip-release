package com.realmatjip.app.core.database.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

/** 즐겨찾기 — 백엔드가 아닌 로컬이 source of truth (개인용, 스펙 §16). */
@Entity(tableName = "favorite_restaurants")
data class FavoriteEntity(
    @PrimaryKey val id: String,
    val name: String,
    val category: String,
    val overallScoreSnapshot: Double?,
    val savedAt: Long,
)

/** 최근 본 맛집 — 최대 30개 유지 (스펙 §17). */
@Entity(tableName = "recent_restaurants")
data class RecentRestaurantEntity(
    @PrimaryKey val id: String,
    val name: String,
    val category: String,
    val overallScoreSnapshot: Double?,
    val viewedAt: Long,
)

/** 상세 화면 캐시 — 오프라인 폴백 + '이전 데이터' 표시 기준 (스펙 §18). */
@Entity(tableName = "restaurant_detail_cache")
data class DetailCacheEntity(
    @PrimaryKey val restaurantId: String,
    val json: String,
    val fetchedAt: Long,
)
