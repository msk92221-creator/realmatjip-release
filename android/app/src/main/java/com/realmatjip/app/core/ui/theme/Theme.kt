package com.realmatjip.app.core.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val GreenPrimary = Color(0xFF2E7D32)
private val GreenContainer = Color(0xFFB7E4C0)

private val LightColors = lightColorScheme(
    primary = GreenPrimary,
    primaryContainer = GreenContainer,
    secondary = Color(0xFF00695C),
    surface = Color(0xFFFCFDF7),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FD694),
    primaryContainer = Color(0xFF1B4A1F),
    secondary = Color(0xFF80CBC4),
)

@Composable
fun RealematjipTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
