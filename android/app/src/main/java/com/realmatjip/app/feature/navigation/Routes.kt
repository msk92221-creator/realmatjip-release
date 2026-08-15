package com.realmatjip.app.feature.navigation

object Routes {
    const val HOME = "home"
    const val MAP = "map"
    const val SEARCH = "search"
    const val FAVORITES = "favorites"
    const val SETTINGS = "settings"
    const val DEVELOPER = "developer"
    const val DETAIL = "restaurant/{restaurantId}"

    fun detail(restaurantId: String) = "restaurant/$restaurantId"

    val bottomTabs = listOf(HOME, MAP, SEARCH, FAVORITES, SETTINGS)
}
