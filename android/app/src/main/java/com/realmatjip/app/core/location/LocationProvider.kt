package com.realmatjip.app.core.location

import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.tasks.await
import javax.inject.Inject
import javax.inject.Singleton

/** 주변 탐색용 위치 — 테스트에서 가짜로 교체한다. */
interface LocationProvider {
    /** 최근 위치(빠름) 우선, 없으면 현재 위치 요청. 실패/권한 없음 → null. */
    suspend fun currentLocation(): Pair<Double, Double>?
}

@Singleton
class FusedLocationProvider @Inject constructor(
    @ApplicationContext private val context: Context,
) : LocationProvider {

    @SuppressLint("MissingPermission") // 호출 전에 컴포저블에서 권한 확인 완료
    override suspend fun currentLocation(): Pair<Double, Double>? = runCatching {
        val client = LocationServices.getFusedLocationProviderClient(context)
        val last = client.lastLocation.await()
        val location = last
            ?: client.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null).await()
        location?.let { it.latitude to it.longitude }
    }.getOrNull()
}
