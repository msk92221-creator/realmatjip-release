package com.realmatjip.app.core.database.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import com.realmatjip.app.core.database.entity.DetailCacheEntity
import com.realmatjip.app.core.database.entity.FavoriteEntity
import com.realmatjip.app.core.database.entity.RecentRestaurantEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface FavoriteDao {
    @Query("SELECT * FROM favorite_restaurants ORDER BY savedAt DESC")
    fun observeAll(): Flow<List<FavoriteEntity>>

    @Query("SELECT COUNT(id) > 0 FROM favorite_restaurants WHERE id = :id")
    fun observeIsFavorite(id: String): Flow<Boolean>

    @Upsert
    suspend fun upsert(entity: FavoriteEntity)

    @Query("DELETE FROM favorite_restaurants WHERE id = :id")
    suspend fun deleteById(id: String)
}

@Dao
interface RecentRestaurantDao {
    @Query("SELECT * FROM recent_restaurants ORDER BY viewedAt DESC LIMIT 30")
    fun observeAll(): Flow<List<RecentRestaurantEntity>>

    @Upsert
    suspend fun upsert(entity: RecentRestaurantEntity)

    @Query(
        "DELETE FROM recent_restaurants WHERE id NOT IN " +
            "(SELECT id FROM recent_restaurants ORDER BY viewedAt DESC LIMIT 30)"
    )
    suspend fun trimToThirty()
}

@Dao
interface DetailCacheDao {
    @Upsert
    suspend fun upsert(entity: DetailCacheEntity)

    @Query("SELECT * FROM restaurant_detail_cache WHERE restaurantId = :restaurantId")
    suspend fun get(restaurantId: String): DetailCacheEntity?

    @Query("DELETE FROM restaurant_detail_cache")
    suspend fun clearAll()
}
