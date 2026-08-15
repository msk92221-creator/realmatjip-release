package com.realmatjip.app

import android.app.Application
import com.realmatjip.app.core.datastore.SettingsDataStore
import com.realmatjip.app.core.network.ConnectionSettingsHolder
import com.realmatjip.app.di.ApplicationScope
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltAndroidApp
class RealmatjipApplication : Application() {

    @Inject lateinit var settingsDataStore: SettingsDataStore

    @Inject lateinit var connectionSettings: ConnectionSettingsHolder

    @Inject
    @ApplicationScope
    lateinit var applicationScope: CoroutineScope

    override fun onCreate() {
        super.onCreate()
        // 설정(DataStore) → 네트워크 계층 동기화. 주소/토큰 변경이 즉시 반영된다.
        applicationScope.launch {
            combine(settingsDataStore.backendUrl, settingsDataStore.apiToken) { url, token ->
                url to token
            }.collect { (url, token) ->
                connectionSettings.update(url, token)
            }
        }
    }
}
