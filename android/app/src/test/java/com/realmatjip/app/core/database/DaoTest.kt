package com.realmatjip.app.core.database

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.realmatjip.app.core.database.entity.DetailCacheEntity
import com.realmatjip.app.core.database.entity.FavoriteEntity
import com.realmatjip.app.core.database.entity.RecentRestaurantEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class FavoriteDaoTest {

    private lateinit var db: AppDatabase

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @After
    fun tearDown() = db.close()

    @Test
    fun `즐겨찾기 추가 조회 삭제`() = runTest {
        val dao = db.favoriteDao()
        dao.upsert(FavoriteEntity("rest-b", "을지면옥", "냉면", 76.6, savedAt = 100))
        dao.upsert(FavoriteEntity("rest-d", "충무노포국밥", "국밥", 78.8, savedAt = 200))

        val all = dao.observeAll().first()
        assertEquals(listOf("rest-d", "rest-b"), all.map { it.id }) // savedAt DESC
        assertTrue(dao.observeIsFavorite("rest-b").first())
        assertFalse(dao.observeIsFavorite("rest-a").first())

        dao.deleteById("rest-d")
        assertEquals(listOf("rest-b"), dao.observeAll().first().map { it.id })
    }

    @Test
    fun `최근 본 맛집 30개 초과분 트림`() = runTest {
        val dao = db.recentRestaurantDao()
        repeat(35) { i ->
            dao.upsert(RecentRestaurantEntity("r-$i", "식당$i", "한식", 70.0, viewedAt = i.toLong()))
        }
        dao.trimToThirty()

        val all = dao.observeAll().first()
        assertEquals(30, all.size)
        assertEquals("r-34", all.first().id) // 최신 우선
    }
}

@RunWith(RobolectricTestRunner::class)
class DetailCacheDaoTest {

    private lateinit var db: AppDatabase

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        db = Room.inMemoryDatabaseBuilder(context, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
    }

    @After
    fun tearDown() = db.close()

    @Test
    fun `상세 캐시 upsert와 갱신`() = runTest {
        val dao = db.detailCacheDao()
        dao.upsert(DetailCacheEntity("rest-b", "{\"v\":1}", fetchedAt = 100))
        assertEquals("{\"v\":1}", dao.get("rest-b")?.json)

        // 재조회 시 같은 키 갱신 (행 증가 아님)
        dao.upsert(DetailCacheEntity("rest-b", "{\"v\":2}", fetchedAt = 200))
        assertEquals("{\"v\":2}", dao.get("rest-b")?.json)
        assertEquals(200L, dao.get("rest-b")?.fetchedAt)

        assertNull(dao.get("rest-a"))
        dao.clearAll()
        assertNull(dao.get("rest-b"))
    }
}
