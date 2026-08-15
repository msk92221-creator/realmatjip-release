package com.realmatjip.app.core.network

import kotlinx.serialization.SerializationException
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/** 모든 화면이 구분해서 표시해야 하는 오류 상태 (스펙 §23). */
enum class ApiError { OFFLINE, TIMEOUT, UNAUTHORIZED, SERVER, PARSE, UNKNOWN }

fun ApiError.userMessage(): String = when (this) {
    ApiError.OFFLINE -> "백엔드에 연결할 수 없습니다. 주소와 네트워크(Tailscale/LAN)를 확인하세요."
    ApiError.TIMEOUT -> "응답이 지연되고 있습니다 (Timeout)."
    ApiError.UNAUTHORIZED -> "인증 실패 — 설정의 API Token을 확인하세요."
    ApiError.SERVER -> "서버 오류가 발생했습니다."
    ApiError.PARSE -> "응답을 해석하지 못했습니다 (앱/서버 버전 불일치 가능)."
    ApiError.UNKNOWN -> "알 수 없는 오류가 발생했습니다."
}

sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Failure(val error: ApiError, val detail: String? = null) : ApiResult<Nothing>
}

suspend fun <T> apiCall(block: suspend () -> T): ApiResult<T> = try {
    ApiResult.Success(block())
} catch (e: retrofit2.HttpException) {
    if (e.code() == 401 || e.code() == 403) {
        ApiResult.Failure(ApiError.UNAUTHORIZED, "HTTP ${e.code()}")
    } else {
        ApiResult.Failure(ApiError.SERVER, "HTTP ${e.code()}")
    }
} catch (e: SocketTimeoutException) {
    ApiResult.Failure(ApiError.TIMEOUT, e.message)
} catch (e: UnknownHostException) {
    ApiResult.Failure(ApiError.OFFLINE, e.message)
} catch (e: ConnectException) {
    ApiResult.Failure(ApiError.OFFLINE, e.message)
} catch (e: IOException) {
    ApiResult.Failure(ApiError.OFFLINE, e.message)
} catch (e: SerializationException) {
    ApiResult.Failure(ApiError.PARSE, e.message)
} catch (e: IllegalArgumentException) {
    // Retrofit baseUrl 오류(설정 오류) 등
    ApiResult.Failure(ApiError.OFFLINE, e.message)
} catch (e: Exception) {
    ApiResult.Failure(ApiError.UNKNOWN, "${e.javaClass.simpleName}: ${e.message}")
}
