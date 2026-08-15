package com.realmatjip.app.core.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.realmatjip.app.core.common.Formatters
import com.realmatjip.app.core.common.evidenceLabel
import com.realmatjip.app.domain.model.Restaurant

/** 맛집 카드 — 점수 중심 요약. Phase 1 목록 API가 제공하는 신호만 표시한다
 * (하위 점수 상세는 상세 화면에서). */
@Composable
fun RestaurantCard(
    restaurant: Restaurant,
    onClick: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth().clickable { onClick(restaurant.id) }) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(restaurant.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                if (restaurant.category.isNotBlank()) {
                    Text(restaurant.category, style = MaterialTheme.typography.bodySmall,
                         color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Spacer(Modifier.height(6.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (restaurant.localBadge) EvidenceChip("로컬맛집")
                    EvidenceChip("근거 ${evidenceLabel(restaurant.evidenceStrength)}")
                    if (restaurant.manipulationScore >= 0.3) {
                        EvidenceChip("비정상 패턴 ${Formatters.percent(restaurant.manipulationScore)}")
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "유효 리뷰 근거 ${Formatters.effReviews(restaurant.nEff)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.width(12.dp))
            ScoreBadge(score = restaurant.primaryScore, size = 64.dp)
        }
    }
}
