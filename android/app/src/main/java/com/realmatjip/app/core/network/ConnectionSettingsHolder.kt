package com.realmatjip.app.core.network

import javax.inject.Inject
import javax.inject.Singleton

/** 현재 연결 설정의 메모리 스냅샷. DataStore 설정이 바뀌면 Application이 갱신한다.

 * APK에 백엔드 주소/토큰을 고정하지 않는 원칙(스펙 §19)의 구현 접점.
 */
@Singleton
class ConnectionSettingsHolder @Inject constructor() {

    @Volatile
    var baseUrl: String = DEFAULT_BACKEND_URL
        private set

    @Volatile
    var token: String = ""
        private set

    fun update(url: String, token: String) {
        this.baseUrl = url.trim().ifEmpty { DEFAULT_BACKEND_URL }
        this.token = token.trim()
    }

    companion object {
        /** 에뮬레이터에서 호스트 머신의 백엔드(Phase 1 uvicorn) 주소 */
        const val DEFAULT_BACKEND_URL = "http://10.0.2.2:8000"
    }
}
