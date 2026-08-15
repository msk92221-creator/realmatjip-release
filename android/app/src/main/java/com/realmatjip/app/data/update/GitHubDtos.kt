package com.realmatjip.app.data.update

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** GitHub Releases API 응답 (releases/latest) — 필요한 필드만. */
@Serializable
data class GitHubRelease(
    @SerialName("tag_name") val tagName: String? = null,
    @SerialName("name") val name: String? = null,
    @SerialName("body") val body: String? = null,
    @SerialName("draft") val draft: Boolean = false,
    @SerialName("prerelease") val prerelease: Boolean = false,
    @SerialName("assets") val assets: List<GitHubAsset> = emptyList(),
)

@Serializable
data class GitHubAsset(
    @SerialName("name") val name: String = "",
    @SerialName("browser_download_url") val browserDownloadUrl: String? = null,
    @SerialName("size") val size: Long = 0,
)
