package com.realmatjip.app.core.datastore

import com.realmatjip.app.domain.model.AdFilter
import kotlinx.coroutines.flow.Flow

/** 앱 설정 인터페이스 — ViewModel은 이 추상에만 의존한다(테스트 대체 가능). */
interface AppSettings {
    val backendUrl: Flow<String>
    val apiToken: Flow<String>
    val defaultAdFilter: Flow<AdFilter>
    val developerMode: Flow<Boolean>

    /** 홈 기준 지역 — 설정 전엔 홈 Top 목록이 비어 있다 (라벨/좌표). */
    val homeRegionLabel: Flow<String>
    val homeRegionLat: Flow<Float>
    val homeRegionLng: Flow<Float>

    suspend fun setBackendUrl(url: String)
    suspend fun setApiToken(token: String)
    suspend fun setDefaultAdFilter(filter: AdFilter)
    suspend fun setDeveloperMode(enabled: Boolean)
    suspend fun setHomeRegion(label: String, lat: Double, lng: Double)
}
