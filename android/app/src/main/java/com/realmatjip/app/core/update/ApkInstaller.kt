package com.realmatjip.app.core.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * APK 설치 인텐트 — 사용자 동의 설치만 (스펙 §10: 자동 설치 금지).
 * 다운로드 파일은 cacheDir/updates 아래 FileProvider로 노출한다.
 */
@Singleton
class ApkInstaller @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    /** 설치 화면을 띄운다. 결과: true = 인텐트 발사 성공 (설치 여부는 사용자 선택). */
    fun launchInstall(apk: File): Boolean {
        if (!apk.exists()) return false
        val uri: Uri = try {
            FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", apk)
        } catch (_: IllegalArgumentException) {
            return false // file_paths 미커버 등
        }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return runCatching {
            context.startActivity(intent)
            true
        }.getOrDefault(false)
    }
}
