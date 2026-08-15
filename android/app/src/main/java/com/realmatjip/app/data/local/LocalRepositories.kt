package com.realmatjip.app.data.local

import com.realmatjip.app.core.database.dao.FavoriteDao
import com.realmatjip.app.core.database.dao.RecentRestaurantDao
import com.realmatjip.app.core.database.entity.FavoriteEntity
import com.realmatjip.app.core.database.entity.RecentRestaurantEntity
import com.realmatjip.app.domain.model.Favorite
import com.realmatjip.app.domain.model.RecentRestaurant
import com.realmatjip.app.domain.repository.FavoriteRepository
import com.realmatjip.app.domain.repository.RecentRepository
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FavoriteRepositoryImpl @Inject constructor(
    private val dao: FavoriteDao,
) : FavoriteRepository {

    override val favorites: Flow<List<Favorite>> =
        dao.observeAll().map { list -> list.map { it.toDomain() } }

    override fun isFavorite(restaurantId: String): Flow<Boolean> =
        dao.observeIsFavorite(restaurantId)

    override suspend fun add(restaurantId: String, name: String, category: String, score: Double?) {
        dao.upsert(
            FavoriteEntity(
                id = restaurantId,
                name = name,
                category = category,
                overallScoreSnapshot = score,
                savedAt = System.currentTimeMillis(),
            )
        )
    }

    override suspend fun remove(restaurantId: String) = dao.deleteById(restaurantId)

    private fun FavoriteEntity.toDomain() = Favorite(
        id = id, name = name, category = category,
        overallScoreSnapshot = overallScoreSnapshot, savedAt = savedAt,
    )
}

@Singleton
class RecentRepositoryImpl @Inject constructor(
    private val dao: RecentRestaurantDao,
) : RecentRepository {

    override val recents: Flow<List<RecentRestaurant>> =
        dao.observeAll().map { list -> list.map { it.toDomain() } }

    override suspend fun record(restaurantId: String, name: String, category: String, score: Double?) {
        dao.upsert(
            RecentRestaurantEntity(
                id = restaurantId,
                name = name,
                category = category,
                overallScoreSnapshot = score,
                viewedAt = System.currentTimeMillis(),
            )
        )
        dao.trimToThirty()
    }

    private fun RecentRestaurantEntity.toDomain() = RecentRestaurant(
        id = id, name = name, category = category,
        overallScoreSnapshot = overallScoreSnapshot, viewedAt = viewedAt,
    )
}
