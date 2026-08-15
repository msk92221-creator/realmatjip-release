package com.realmatjip.app.core.network

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.reflect.KClass

/** 동적 baseUrl Retrofit 클라이언트 — 설정에서 백엔드 주소를 바꾸면 서비스를 재생성한다. */
@Singleton
class ApiClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    private val json: Json,
    private val settings: ConnectionSettingsHolder,
) {

    private val lock = Any()
    private var retrofit: Retrofit? = null
    private var builtForUrl: String? = null
    private val services = ConcurrentHashMap<KClass<*>, Any>()

    fun <T : Any> service(api: KClass<T>): T {
        val url = normalize(settings.baseUrl)
        synchronized(lock) {
            if (retrofit == null || builtForUrl != url) {
                builtForUrl = url
                services.clear()
                retrofit = Retrofit.Builder()
                    .baseUrl(url)
                    .client(okHttpClient)
                    .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
                    .build()
            }
            @Suppress("UNCHECKED_CAST")
            return services.getOrPut(api) { retrofit!!.create(api.java) } as T
        }
    }

    private fun normalize(url: String): String {
        val withScheme = if (url.startsWith("http://") || url.startsWith("https://")) url
        else "http://$url"
        return if (withScheme.endsWith("/")) withScheme else "$withScheme/"
    }
}
