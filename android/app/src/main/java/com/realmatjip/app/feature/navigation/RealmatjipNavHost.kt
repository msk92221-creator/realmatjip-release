package com.realmatjip.app.feature.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.realmatjip.app.feature.developer.DeveloperScreen
import com.realmatjip.app.feature.favorites.FavoritesScreen
import com.realmatjip.app.feature.home.HomeScreen
import com.realmatjip.app.feature.map.MapScreen
import com.realmatjip.app.feature.restaurantdetail.RestaurantDetailScreen
import com.realmatjip.app.feature.search.SearchScreen
import com.realmatjip.app.feature.settings.SettingsScreen

private data class BottomTab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    BottomTab(Routes.HOME, "홈", Icons.Filled.Home),
    BottomTab(Routes.MAP, "지도", Icons.Filled.Map),
    BottomTab(Routes.SEARCH, "검색", Icons.Filled.Search),
    BottomTab(Routes.FAVORITES, "저장", Icons.Filled.Favorite),
    BottomTab(Routes.SETTINGS, "설정", Icons.Filled.Settings),
)

@Composable
fun RealematjipApp() {
    val navController: NavHostController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    val showBottomBar = currentRoute in Routes.bottomTabs

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute == tab.route,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Routes.HOME,
            modifier = Modifier.padding(padding),
        ) {
            composable(Routes.HOME) {
                HomeScreen(
                    onRestaurantClick = { navController.navigate(Routes.detail(it)) },
                )
            }
            composable(Routes.MAP) {
                MapScreen(
                    onRestaurantClick = { navController.navigate(Routes.detail(it)) },
                )
            }
            composable(Routes.SEARCH) {
                SearchScreen(
                    onRestaurantClick = { navController.navigate(Routes.detail(it)) },
                )
            }
            composable(Routes.FAVORITES) {
                FavoritesScreen(
                    onRestaurantClick = { navController.navigate(Routes.detail(it)) },
                )
            }
            composable(Routes.SETTINGS) {
                SettingsScreen(
                    onOpenDeveloper = { navController.navigate(Routes.DEVELOPER) },
                )
            }
            composable(Routes.DEVELOPER) {
                DeveloperScreen(onBack = { navController.popBackStack() })
            }
            composable(
                route = Routes.DETAIL,
                arguments = listOf(navArgument("restaurantId") { defaultValue = "" }),
            ) { entry ->
                val restaurantId = entry.arguments?.getString("restaurantId").orEmpty()
                RestaurantDetailScreen(
                    restaurantId = restaurantId,
                    onBack = { navController.popBackStack() },
                )
            }
        }
    }
}
