package com.realmatjip.app.feature.favorites

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.realmatjip.app.core.common.Formatters
import com.realmatjip.app.core.ui.components.EmptyView
import com.realmatjip.app.core.ui.components.SectionHeader

/** 저장함 — Room 로컬 즐겨찾기 (스펙 §16). */
@Composable
fun FavoritesScreen(
    onRestaurantClick: (String) -> Unit,
    viewModel: FavoritesViewModel = hiltViewModel(),
) {
    val favorites by viewModel.favorites.collectAsState()

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        SectionHeader("저장한 맛집")
        if (favorites.isEmpty()) {
            EmptyView(text = "저장한 맛집이 없습니다\n식당 상세에서 ♡를 눌러 저장하세요")
        } else {
            LazyColumn(
                contentPadding = PaddingValues(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(favorites, key = { it.id }) { favorite ->
                    Card(
                        Modifier
                            .fillMaxWidth()
                            .clickable { onRestaurantClick(favorite.id) },
                    ) {
                        Row(
                            modifier = Modifier.padding(start = 12.dp, top = 12.dp, bottom = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    favorite.name,
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.Bold,
                                )
                                if (favorite.category.isNotBlank()) {
                                    Text(
                                        favorite.category,
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                            Text(
                                Formatters.score(favorite.overallScoreSnapshot),
                                style = MaterialTheme.typography.titleMedium,
                                color = MaterialTheme.colorScheme.primary,
                            )
                            IconButton(onClick = { viewModel.remove(favorite.id) }) {
                                Icon(Icons.Filled.Delete, contentDescription = "삭제")
                            }
                        }
                    }
                }
            }
        }
    }
}
