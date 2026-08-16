package com.realmatjip.app.di

import com.realmatjip.app.core.datastore.AppSettings
import com.realmatjip.app.core.datastore.SettingsDataStore
import com.realmatjip.app.data.admin.AdminRepositoryImpl
import com.realmatjip.app.data.local.FavoriteRepositoryImpl
import com.realmatjip.app.data.local.RecentRepositoryImpl
import com.realmatjip.app.data.providers.ProviderRepositoryImpl
import com.realmatjip.app.data.restaurant.RestaurantRepositoryImpl
import com.realmatjip.app.data.update.DataStoreUpdateCheckStore
import com.realmatjip.app.data.update.GitHubUpdateRepository
import com.realmatjip.app.data.update.UpdateCheckStore
import com.realmatjip.app.data.update.UpdateRepository
import com.realmatjip.app.domain.repository.AdminRepository
import com.realmatjip.app.domain.repository.FavoriteRepository
import com.realmatjip.app.domain.repository.ProviderRepository
import com.realmatjip.app.domain.repository.RecentRepository
import com.realmatjip.app.domain.repository.RestaurantRepository
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {

    @Binds
    @Singleton
    abstract fun bindRestaurantRepository(impl: RestaurantRepositoryImpl): RestaurantRepository

    @Binds
    @Singleton
    abstract fun bindAdminRepository(impl: AdminRepositoryImpl): AdminRepository

    @Binds
    @Singleton
    abstract fun bindFavoriteRepository(impl: FavoriteRepositoryImpl): FavoriteRepository

    @Binds
    @Singleton
    abstract fun bindRecentRepository(impl: RecentRepositoryImpl): RecentRepository

    @Binds
    @Singleton
    abstract fun bindUpdateRepository(impl: GitHubUpdateRepository): UpdateRepository

    @Binds
    @Singleton
    abstract fun bindUpdateCheckStore(impl: DataStoreUpdateCheckStore): UpdateCheckStore

    @Binds
    @Singleton
    abstract fun bindLocationProvider(
        impl: com.realmatjip.app.core.location.FusedLocationProvider,
    ): com.realmatjip.app.core.location.LocationProvider

    @Binds
    @Singleton
    abstract fun bindAppSettings(impl: SettingsDataStore): AppSettings

    @Binds
    @Singleton
    abstract fun bindProviderRepository(impl: ProviderRepositoryImpl): ProviderRepository

    companion object {
        /** Phase 4 업데이트 시스템 값 — 릴리즈 저장소 slug는 여기 한 곳에서 관리 (D2). */
        @Provides
        @Named("currentVersion")
        fun provideCurrentVersion(): String =
            com.realmatjip.app.BuildConfig.VERSION_NAME

        @Provides
        @Named("releaseRepoSlug")
        fun provideReleaseRepoSlug(): String =
            GitHubUpdateRepository.DEFAULT_RELEASE_REPO
    }
}
