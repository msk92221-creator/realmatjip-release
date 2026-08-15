package com.realmatjip.app.di

import android.content.Context
import androidx.room.Room
import com.realmatjip.app.core.database.AppDatabase
import com.realmatjip.app.core.database.dao.DetailCacheDao
import com.realmatjip.app.core.database.dao.FavoriteDao
import com.realmatjip.app.core.database.dao.RecentRestaurantDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "realmatjip.db")
            .fallbackToDestructiveMigration() // 개인용 v1 — 스키마 진화 시 마이그레이션 작성
            .build()

    @Provides
    fun provideFavoriteDao(db: AppDatabase): FavoriteDao = db.favoriteDao()

    @Provides
    fun provideRecentDao(db: AppDatabase): RecentRestaurantDao = db.recentRestaurantDao()

    @Provides
    fun provideDetailCacheDao(db: AppDatabase): DetailCacheDao = db.detailCacheDao()
}
