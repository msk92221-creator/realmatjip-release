package com.realmatjip.app.core.datastore

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.realmatjip.app.core.network.ConnectionSettingsHolder
import com.realmatjip.app.domain.model.AdFilter
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.settingsDataStore by preferencesDataStore("realmatjip_settings")

/** 앱 설정 — 백엔드 주소/토큰/기본 광고 필터/개발자 모드 (스펙 §19, §22). */
@Singleton
class SettingsDataStore @Inject constructor(
    @ApplicationContext private val context: Context,
) : AppSettings {
    private object Keys {
        val BACKEND_URL = stringPreferencesKey("backend_url")
        val API_TOKEN = stringPreferencesKey("api_token")
        val DEFAULT_AD_FILTER = stringPreferencesKey("default_ad_filter")
        val DEVELOPER_MODE = booleanPreferencesKey("developer_mode")
        val HOME_REGION_LABEL = stringPreferencesKey("home_region_label")
        val HOME_REGION_LAT = floatPreferencesKey("home_region_lat")
        val HOME_REGION_LNG = floatPreferencesKey("home_region_lng")
    }

    override val backendUrl: Flow<String> = context.settingsDataStore.data.map { prefs ->
        // 빈 값은 "미설정"과 같게 취급 — 설정 화면에서 주소를 지우고 저장하면 기본값으로 되돌아간다.
        prefs[Keys.BACKEND_URL]?.takeIf { it.isNotBlank() }
            ?: ConnectionSettingsHolder.DEFAULT_BACKEND_URL
    }

    override val apiToken: Flow<String> = context.settingsDataStore.data.map { prefs ->
        prefs[Keys.API_TOKEN] ?: ""
    }

    override val defaultAdFilter: Flow<AdFilter> = context.settingsDataStore.data.map { prefs ->
        AdFilter.fromName(prefs[Keys.DEFAULT_AD_FILTER]) ?: AdFilter.BASIC
    }

    override val developerMode: Flow<Boolean> = context.settingsDataStore.data.map { prefs ->
        prefs[Keys.DEVELOPER_MODE] ?: false
    }

    override suspend fun setBackendUrl(url: String) {
        context.settingsDataStore.edit { it[Keys.BACKEND_URL] = url.trim() }
    }

    override suspend fun setApiToken(token: String) {
        context.settingsDataStore.edit { it[Keys.API_TOKEN] = token.trim() }
    }

    override suspend fun setDefaultAdFilter(filter: AdFilter) {
        context.settingsDataStore.edit { it[Keys.DEFAULT_AD_FILTER] = filter.name }
    }

    override suspend fun setDeveloperMode(enabled: Boolean) {
        context.settingsDataStore.edit { it[Keys.DEVELOPER_MODE] = enabled }
    }

    override val homeRegionLabel: Flow<String> = context.settingsDataStore.data.map { prefs ->
        prefs[Keys.HOME_REGION_LABEL] ?: ""
    }
    override val homeRegionLat: Flow<Float> = context.settingsDataStore.data.map { prefs ->
        prefs[Keys.HOME_REGION_LAT] ?: 0f
    }
    override val homeRegionLng: Flow<Float> = context.settingsDataStore.data.map { prefs ->
        prefs[Keys.HOME_REGION_LNG] ?: 0f
    }

    override suspend fun setHomeRegion(label: String, lat: Double, lng: Double) {
        context.settingsDataStore.edit { prefs ->
            prefs[Keys.HOME_REGION_LABEL] = label
            prefs[Keys.HOME_REGION_LAT] = lat.toFloat()
            prefs[Keys.HOME_REGION_LNG] = lng.toFloat()
        }
    }
}
