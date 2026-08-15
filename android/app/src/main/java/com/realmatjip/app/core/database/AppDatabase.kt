package com.realmatjip.app.core.database

import androidx.room.Database
import androidx.room.RoomDatabase
import com.realmatjip.app.core.database.dao.DetailCacheDao
import com.realmatjip.app.core.database.dao.FavoriteDao
import com.realmatjip.app.core.database.dao.RecentRestaurantDao
import com.realmatjip.app.core.database.entity.DetailCacheEntity
import com.realmatjip.app.core.database.entity.FavoriteEntity
import com.realmatjip.app.core.database.entity.RecentRestaurantEntity

@Database(
    entities = [
        FavoriteEntity::class,
        RecentRestaurantEntity::class,
        DetailCacheEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun favoriteDao(): FavoriteDao
    abstract fun recentRestaurantDao(): RecentRestaurantDao
    abstract fun detailCacheDao(): DetailCacheDao
}
