package com.realmatjip.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.realmatjip.app.core.ui.components.RestaurantCard
import com.realmatjip.app.domain.model.Restaurant
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/** 핵심 카드 UI 스모크 — 점수·이름·근거 라벨 렌더링과 클릭 콜백. */
class RestaurantCardUiTest {

    @get:Rule
    val composeRule = createComposeRule()

    private val sample = Restaurant(
        id = "rest-b", name = "을지면옥", category = "평양냉면",
        lat = 37.56, lng = 126.99, overallA = 76.6, overallB = 74.0,
        nRaw = 34, nEff = 20.5, evidenceStrength = 0.72,
        localBadge = true, manipulationScore = 0.04,
    )

    @Test
    fun restaurantCard_displaysScoreAndCallsBack() {
        var clicked: String? = null
        composeRule.setContent {
            RestaurantCard(restaurant = sample, onClick = { clicked = it })
        }

        composeRule.onNodeWithText("을지면옥").assertIsDisplayed()
        composeRule.onNodeWithText("77").assertIsDisplayed() // 76.6 → 정수 배지
        composeRule.onNodeWithText("로컬맛집").assertIsDisplayed()

        composeRule.onNodeWithText("을지면옥").performClick()
        composeRule.runOnIdle { assertEquals("rest-b", clicked) }
    }
}
