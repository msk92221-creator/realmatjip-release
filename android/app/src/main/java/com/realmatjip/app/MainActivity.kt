package com.realmatjip.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.realmatjip.app.core.ui.theme.RealematjipTheme
import com.realmatjip.app.feature.navigation.RealematjipApp
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            RealematjipTheme {
                RealematjipApp()
            }
        }
    }
}
