package com.realmatjip.app.core.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.realmatjip.app.core.common.Formatters

/** 점수 밴드 색 — 표시용. 점수 자체는 백엔드가 source of truth. */
fun scoreColor(score: Double?): Color = when {
    score == null -> Color.Gray
    score >= 80 -> Color(0xFF2E7D32)
    score >= 65 -> Color(0xFF00897B)
    score >= 50 -> Color(0xFFF9A825)
    else -> Color(0xFF8D6E63)
}

/** 큰 원형 점수 배지 — raw 별점 대신 Overall Score를 시각적으로 우선 표시 (스펙 §8). */
@Composable
fun ScoreBadge(
    score: Double?,
    modifier: Modifier = Modifier,
    size: Dp = 56.dp,
) {
    Box(
        modifier = modifier
            .size(size)
            .background(scoreColor(score), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = Formatters.scoreInt(score),
            color = Color.White,
            fontSize = (size.value * 0.34).sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
fun EvidenceChip(
    label: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .background(MaterialTheme.colorScheme.secondaryContainer, CircleShape)
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSecondaryContainer,
        )
    }
}
