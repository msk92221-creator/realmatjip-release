package com.realmatjip.app.core.network

import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/** DataStore에서 관리되는 토큰만 헤더에 붙인다. 토큰이 비어 있으면 미첨부(로컬 개발). */
class AuthInterceptor @Inject constructor(
    private val holder: ConnectionSettingsHolder,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val builder = chain.request().newBuilder()
        val token = holder.token
        if (token.isNotBlank()) {
            builder.header("Authorization", "Bearer $token")
        }
        return chain.proceed(builder.build())
    }
}
