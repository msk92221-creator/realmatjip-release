package com.realmatjip.app.data.update

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import javax.inject.Inject
import javax.inject.Singleton

private val Context.updateCheckDataStore by preferencesDataStore("realmatjip_update")

/** 업데이트 확인 기록 — 24h 스로틀/ETag 조건부 요청에 필요한 최소 상태만 보관.
 *  lastReleaseBody: ETag가 304로 바뀐 게 없을 때 재판정에 쓴다 (설치 안 됐을 수 있으므로). */
interface UpdateCheckStore {
    suspend fun lastCheckEpochMs(): Long
    suspend fun etag(): String
    suspend fun lastReleaseBody(): String
    suspend fun save(etag: String, checkedAtMs: Long, releaseBody: String = "")
}

@Singleton
class DataStoreUpdateCheckStore @Inject constructor(
    @ApplicationContext private val context: Context,
) : UpdateCheckStore {
    private object Keys {
        val ETAG = stringPreferencesKey("etag")
        val CHECKED_AT = longPreferencesKey("checked_at")
        val LAST_BODY = stringPreferencesKey("last_release_body")
    }

    override suspend fun lastCheckEpochMs(): Long =
        context.updateCheckDataStore.data.first()[Keys.CHECKED_AT] ?: 0L

    override suspend fun etag(): String =
        context.updateCheckDataStore.data.first()[Keys.ETAG] ?: ""

    override suspend fun lastReleaseBody(): String =
        context.updateCheckDataStore.data.first()[Keys.LAST_BODY] ?: ""

    override suspend fun save(etag: String, checkedAtMs: Long, releaseBody: String) {
        context.updateCheckDataStore.edit { prefs ->
            prefs[Keys.ETAG] = etag
            prefs[Keys.CHECKED_AT] = checkedAtMs
            prefs[Keys.LAST_BODY] = releaseBody
        }
    }
}
